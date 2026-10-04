from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda *_a, **_k: None

from smart_finance.config import FinanceConfig
from smart_finance.decisions import build_sku_decisions, load_demand_matches
from smart_finance.metrics import compute_health_score, compute_snapshot
from smart_finance.output import write_dashboard, write_json, write_kpis_csv, write_rows_csv
from smart_finance.parsers import (
    parse_cash_position,
    parse_inventory_cost_map,
    parse_monthly_obligations,
    parse_provider_balances,
)
from smart_finance.v2_parsers import parse_v2_cash, parse_v2_debts, parse_v2_obligations
from smart_finance.sheets import GoogleSheetsReader
from smart_finance.shopify_finance import (
    ShopifyFinanceClient,
    ShopifyFinanceConfig,
    enrich_sales_with_cogs,
    summarize_inventory,
    summarize_orders,
)


def main() -> int:
    load_dotenv(".env")
    parser = argparse.ArgumentParser(description="Sportland Smart Finance v0.2 — Shopify-first hybrid + Finanzas v2")
    parser.add_argument("--fixture", help="Hybrid offline fixture JSON")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--month", type=int, default=date.today().month)
    parser.add_argument("--skip-scope-check", action="store_true")
    args = parser.parse_args()

    cfg = FinanceConfig.from_env()

    if args.fixture:
        fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        cash = fixture["cash"]
        obligations = fixture["obligations"]
        provider_balances = fixture["provider_balances"]
        shopify = fixture["shopify"]
        manual_debts = cfg.manual_debts
    else:
        errors = cfg.validate()
        shop_cfg = ShopifyFinanceConfig.from_env()
        errors += shop_cfg.validate()
        if errors:
            print("CONFIG ERROR")
            for e in errors:
                print(f"- {e}")
            return 2

        print(f"1/5 Reading external finance data — schema={cfg.schema}...")
        reader = GoogleSheetsReader(cfg.spreadsheet_id, cfg.service_account_file)

        if cfg.schema == "v2":
            debts_rows = reader.read(f"'{cfg.debts_sheet}'!A:J")
            payments_rows = reader.read(f"'{cfg.payments_sheet}'!A:K")
            cash_rows = reader.read(f"'{cfg.cashflow_sheet}'!A:H")
            provider_balances = parse_v2_debts(debts_rows)
            cash = parse_v2_cash(cash_rows)
            obligations = parse_v2_obligations(
                payments_rows,
                as_of=date.today(),
                horizon_days=cfg.horizon_days,
            )
            # Sprint 1 Deudas is authoritative; avoid double-counting finance_rules debts.
            manual_debts = []
            cost_fallback = {}
        else:
            providers_rows = reader.read(f"'{cfg.providers_sheet}'!A:AZ")
            payments_rows = reader.read(f"'{cfg.payments_sheet}'!A:AZ")
            cash_rows = reader.read(f"'{cfg.cashflow_sheet}'!A:AZ")
            inventory_rows = []
            if cfg.spreadsheet_cost_fallback:
                inventory_rows = reader.read(f"'{cfg.inventory_sheet}'!A:AD")
            cash = parse_cash_position(cash_rows, args.year, args.month)
            obligations = parse_monthly_obligations(payments_rows, args.year, args.month)
            provider_balances = parse_provider_balances(providers_rows)
            cost_fallback = parse_inventory_cost_map(inventory_rows) if inventory_rows else {}
            manual_debts = cfg.manual_debts

        print("2/5 Connecting to Shopify...")
        client = ShopifyFinanceClient(shop_cfg)
        if not args.skip_scope_check:
            scope = client.validate_scopes()
            if scope["missing"]:
                print("SHOPIFY SCOPE ERROR")
                print("Missing scopes: " + ", ".join(scope["missing"]))
                print("Granted scopes: " + ", ".join(scope["granted"]))
                print("Add read_orders to the Shopify app version/scopes, then run again.")
                return 3

        print("3/5 Reading Shopify orders and inventory...")
        variants = client.fetch_variants()
        orders = client.fetch_orders(days=max(60, shop_cfg.lookback_days))
        inventory = summarize_inventory(variants, cost_fallback)
        order_summary = summarize_orders(orders, now=datetime.now(timezone.utc))
        order_summary = enrich_sales_with_cogs(order_summary, inventory)
        shopify = {
            "orders": order_summary,
            "inventory": inventory,
            "variant_count": len(variants),
            "order_records": len(orders),
        }

    print("4/5 Computing hybrid KPIs and SKU decisions...")
    snapshot = compute_snapshot(
        shopify=shopify,
        cash=cash,
        obligations=obligations,
        provider_balances=provider_balances,
        reserve_cash=cfg.reserve_cash,
        manual_debts=manual_debts,
    )
    snapshot["finance_schema"] = cfg.schema
    health = compute_health_score(snapshot)
    snapshot["financial_health"] = health

    matches = load_demand_matches(cfg.matches_csv)
    decisions = build_sku_decisions(matches, shopify, snapshot)

    print("5/5 Writing artifacts...")
    out_dir = Path(cfg.artifacts_dir)
    write_json(out_dir / "financial_snapshot.json", snapshot)
    write_json(out_dir / "shopify_finance_snapshot.json", shopify)
    write_kpis_csv(out_dir / "financial_kpis.csv", snapshot, health)
    write_rows_csv(out_dir / "shopify_sku_performance.csv", (shopify.get("orders") or {}).get("sku_performance", []), "sku\n")
    write_rows_csv(out_dir / "shopify_inventory_finance.csv", (shopify.get("inventory") or {}).get("variants", []), "sku\n")
    write_rows_csv(out_dir / "smart_finance_decisions.csv", decisions, "sku,decision,reason\n")
    write_json(out_dir / "source_provenance.json", snapshot.get("data_sources", {}))
    write_dashboard(out_dir / "finance_dashboard.html", snapshot, health, decisions)

    k = snapshot["kpis"]
    print("Sportland Smart Finance — Shopify-first + Finanzas v2")
    print(f"Finance schema: {cfg.schema}")
    print(f"Health: {health['score']} / 100 ({health['status']})")
    print(f"Sales 30d (Shopify): {k['sales_30d']}")
    print(f"Orders 30d (Shopify): {k['orders_30d']}")
    print(f"Inventory units (Shopify): {k['inventory_units']}")
    print(f"Cash (Finanzas): {k['cash_available']}")
    print(f"30d obligations (Finanzas): {k['projected_obligations_30d']}")
    print(f"Known debt (Finanzas): {k['known_debt_total']}")
    print(f"Artifacts: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
