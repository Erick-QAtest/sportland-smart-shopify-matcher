from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


def _money(node: Any) -> float:
    if not node:
        return 0.0
    if isinstance(node, dict) and "shopMoney" in node:
        node = node.get("shopMoney")
    if isinstance(node, dict):
        try:
            return float(node.get("amount") or 0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(node)
    except (TypeError, ValueError):
        return 0.0


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_shop_host(value: str) -> str:
    v = (value or "").strip().replace("https://", "").replace("http://", "").strip("/")
    if not v:
        return ""
    if ".myshopify.com" not in v:
        v = f"{v}.myshopify.com"
    return v


@dataclass
class ShopifyFinanceConfig:
    shop: str = ""
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    api_version: str = "2026-07"
    lookback_days: int = 60
    request_timeout: int = 45

    @classmethod
    def from_env(cls) -> "ShopifyFinanceConfig":
        return cls(
            shop=normalize_shop_host(os.getenv("SHOPIFY_SHOP", os.getenv("SHOPIFY_HOST", ""))),
            client_id=os.getenv("SHOPIFY_CLIENT_ID", "").strip(),
            client_secret=os.getenv("SHOPIFY_CLIENT_SECRET", "").strip(),
            access_token=os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip(),
            api_version=os.getenv("SHOPIFY_API_VERSION", "2026-07").strip() or "2026-07",
            lookback_days=int(os.getenv("FINANCE_SHOPIFY_LOOKBACK_DAYS", "60") or 60),
            request_timeout=int(os.getenv("FINANCE_SHOPIFY_TIMEOUT", "45") or 45),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.shop:
            errors.append("SHOPIFY_SHOP is required")
        if not self.access_token and not (self.client_id and self.client_secret):
            errors.append("Set SHOPIFY_ADMIN_ACCESS_TOKEN or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET")
        return errors


class ShopifyFinanceClient:
    """Read-only Shopify Admin GraphQL client for financial reporting."""

    REQUIRED_SCOPES = {"read_orders", "read_products"}

    def __init__(self, cfg: ShopifyFinanceConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self._token = cfg.access_token or None

    @property
    def graphql_url(self) -> str:
        return f"https://{self.cfg.shop}/admin/api/{self.cfg.api_version}/graphql.json"

    def _get_token(self) -> str:
        if self._token:
            return self._token
        url = f"https://{self.cfg.shop}/admin/oauth/access_token"
        response = self.session.post(
            url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret,
            },
            timeout=self.cfg.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"Shopify token response did not include access_token: {payload}")
        self._token = token
        return token

    def graphql(self, query: str, variables: dict[str, Any] | None = None, retries: int = 4) -> dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        for attempt in range(retries):
            r = self.session.post(
                self.graphql_url,
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Access-Token": self._get_token(),
                },
                json=payload,
                timeout=self.cfg.request_timeout,
            )
            if r.status_code in {429, 500, 502, 503, 504} and attempt < retries - 1:
                time.sleep(min(2 ** attempt, 8))
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("errors"):
                msg = "; ".join(str(e.get("message", e)) for e in data["errors"])
                if "THROTTLED" in msg.upper() and attempt < retries - 1:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError(f"Shopify GraphQL error: {msg}")
            return data.get("data") or {}
        raise RuntimeError("Shopify GraphQL request exhausted retries")

    def access_scopes(self) -> set[str]:
        data = self.graphql("query { currentAppInstallation { accessScopes { handle } } }")
        rows = ((data.get("currentAppInstallation") or {}).get("accessScopes") or [])
        return {str(x.get("handle")) for x in rows if x.get("handle")}

    def validate_scopes(self) -> dict[str, Any]:
        scopes = self.access_scopes()
        missing = sorted(self.REQUIRED_SCOPES - scopes)
        return {
            "granted": sorted(scopes),
            "required": sorted(self.REQUIRED_SCOPES),
            "missing": missing,
            "ok": not missing,
        }

    def fetch_orders(self, days: int | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
        days = days or self.cfg.lookback_days
        now = now or datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        search = f"created_at:>={_iso(start)}"
        query = """
        query FinanceOrders($first:Int!, $after:String, $query:String!) {
          orders(first:$first, after:$after, query:$query, sortKey:CREATED_AT) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id name createdAt cancelledAt
              currentSubtotalPriceSet { shopMoney { amount currencyCode } }
              currentTotalDiscountsSet { shopMoney { amount currencyCode } }
              currentTotalPriceSet { shopMoney { amount currencyCode } }
              originalTotalPriceSet { shopMoney { amount currencyCode } }
              lineItems(first:100) {
                nodes {
                  title sku quantity currentQuantity
                  originalTotalSet { shopMoney { amount currencyCode } }
                  priceAfterAllDiscountsBeforeTaxesSet { shopMoney { amount currencyCode } }
                  totalDiscountSet { shopMoney { amount currencyCode } }
                }
              }
            }
          }
        }
        """
        after = None
        out: list[dict[str, Any]] = []
        while True:
            data = self.graphql(query, {"first": 100, "after": after, "query": search})
            conn = data.get("orders") or {}
            out.extend(conn.get("nodes") or [])
            page = conn.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            after = page.get("endCursor")
            if not after:
                break
        return out

    def fetch_variants(self) -> list[dict[str, Any]]:
        query = """
        query FinanceVariants($first:Int!, $after:String) {
          productVariants(first:$first, after:$after, sortKey:ID) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id sku title price compareAtPrice inventoryQuantity
              product { id title handle status }
              inventoryItem { unitCost { amount currencyCode } }
            }
          }
        }
        """
        after = None
        out: list[dict[str, Any]] = []
        while True:
            data = self.graphql(query, {"first": 100, "after": after})
            conn = data.get("productVariants") or {}
            out.extend(conn.get("nodes") or [])
            page = conn.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            after = page.get("endCursor")
            if not after:
                break
        return out


def summarize_orders(orders: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """Build trailing 30d and previous-30d metrics from up to 60 days of orders."""
    now = now or datetime.now(timezone.utc)
    cut30 = now - timedelta(days=30)
    cut60 = now - timedelta(days=60)
    periods = {
        "current": {"start": cut30, "end": now},
        "previous": {"start": cut60, "end": cut30},
    }

    def empty() -> dict[str, Any]:
        return {
            "orders": 0,
            "gross_sales": 0.0,
            "net_product_sales": 0.0,
            "total_sales": 0.0,
            "discounts": 0.0,
            "order_reductions": 0.0,
            "units_sold": 0,
            "estimated_cogs": 0.0,
            "gross_margin": 0.0,
            "gross_margin_pct": None,
        }

    agg = {k: empty() for k in periods}
    sku_perf: dict[str, dict[str, Any]] = {}

    for order in orders:
        try:
            created = datetime.fromisoformat(str(order.get("createdAt")).replace("Z", "+00:00"))
        except Exception:
            continue
        bucket = None
        for key, p in periods.items():
            if p["start"] <= created < p["end"]:
                bucket = key
                break
        if bucket is None:
            continue
        a = agg[bucket]
        current_total = _money(order.get("currentTotalPriceSet"))
        original_total = _money(order.get("originalTotalPriceSet"))
        current_subtotal = _money(order.get("currentSubtotalPriceSet"))
        discounts = _money(order.get("currentTotalDiscountsSet"))
        if not order.get("cancelledAt") and current_total > 0:
            a["orders"] += 1
        a["gross_sales"] += original_total
        a["net_product_sales"] += current_subtotal
        a["total_sales"] += current_total
        a["discounts"] += discounts
        a["order_reductions"] += max(0.0, original_total - current_total)

        for li in ((order.get("lineItems") or {}).get("nodes") or []):
            qty = int(li.get("currentQuantity") or 0)
            if qty <= 0:
                continue
            a["units_sold"] += qty
            sku = (li.get("sku") or "").strip()
            title = li.get("title") or ""
            net = _money(li.get("priceAfterAllDiscountsBeforeTaxesSet"))
            original = _money(li.get("originalTotalSet"))
            if sku:
                row = sku_perf.setdefault(
                    sku,
                    {
                        "sku": sku,
                        "product_title": title,
                        "units_30d": 0,
                        "units_prev_30d": 0,
                        "net_sales_30d": 0.0,
                        "net_sales_prev_30d": 0.0,
                        "gross_sales_30d": 0.0,
                    },
                )
                if bucket == "current":
                    row["units_30d"] += qty
                    row["net_sales_30d"] += net
                    row["gross_sales_30d"] += original
                else:
                    row["units_prev_30d"] += qty
                    row["net_sales_prev_30d"] += net

    for a in agg.values():
        a["average_order_value"] = (a["total_sales"] / a["orders"]) if a["orders"] else None
        for k in ("gross_sales", "net_product_sales", "total_sales", "discounts", "order_reductions"):
            a[k] = round(a[k], 2)
        if a["average_order_value"] is not None:
            a["average_order_value"] = round(a["average_order_value"], 2)

    return {
        "as_of": now.isoformat(),
        "current_30d": agg["current"],
        "previous_30d": agg["previous"],
        "sku_performance": list(sku_perf.values()),
    }


def summarize_inventory(
    variants: list[dict[str, Any]],
    spreadsheet_cost_map: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    spreadsheet_cost_map = spreadsheet_cost_map or {}
    rows: list[dict[str, Any]] = []
    units = 0
    retail_value = 0.0
    cost_value = 0.0
    known_cost_units = 0
    missing_cost_units = 0
    potential_margin = 0.0

    for v in variants:
        product = v.get("product") or {}
        if str(product.get("status") or "").upper() not in {"ACTIVE", ""}:
            continue
        sku = (v.get("sku") or "").strip()
        stock = max(0, int(v.get("inventoryQuantity") or 0))
        price = float(v.get("price") or 0)
        unit_cost_node = ((v.get("inventoryItem") or {}).get("unitCost") or {})
        shopify_cost = float(unit_cost_node.get("amount")) if unit_cost_node.get("amount") not in (None, "") else None
        fallback = (spreadsheet_cost_map.get(sku) or {}).get("cost") if sku else None
        cost = shopify_cost if shopify_cost is not None else fallback
        cost_source = "shopify" if shopify_cost is not None else ("finance_sheet_fallback" if fallback is not None else "missing")
        margin_pct = ((price - cost) / price) if (cost is not None and price > 0) else None
        row = {
            "sku": sku,
            "product_title": product.get("title") or "",
            "variant_title": v.get("title") or "",
            "inventory_quantity": stock,
            "price": price,
            "compare_at_price": float(v.get("compareAtPrice") or 0) if v.get("compareAtPrice") not in (None, "") else None,
            "unit_cost": cost,
            "cost_source": cost_source,
            "margin_pct": margin_pct,
        }
        rows.append(row)
        if stock > 0:
            units += stock
            retail_value += stock * price
            if cost is None:
                missing_cost_units += stock
            else:
                known_cost_units += stock
                cost_value += stock * cost
                potential_margin += stock * max(0, price - cost)

    return {
        "units": units,
        "retail_value": round(retail_value, 2),
        "cost_value_known": round(cost_value, 2),
        "known_cost_units": known_cost_units,
        "missing_cost_units": missing_cost_units,
        "potential_margin_known": round(potential_margin, 2),
        "variants": rows,
    }


def enrich_sales_with_cogs(order_summary: dict[str, Any], inventory_summary: dict[str, Any]) -> dict[str, Any]:
    cost_by_sku = {
        r["sku"]: r.get("unit_cost")
        for r in inventory_summary.get("variants", [])
        if r.get("sku") and r.get("unit_cost") is not None
    }
    current_cogs = 0.0
    previous_cogs = 0.0
    missing_units_current = 0
    missing_units_previous = 0
    for row in order_summary.get("sku_performance", []):
        sku = row.get("sku")
        cost = cost_by_sku.get(sku)
        if cost is None:
            missing_units_current += int(row.get("units_30d") or 0)
            missing_units_previous += int(row.get("units_prev_30d") or 0)
            continue
        current_cogs += cost * int(row.get("units_30d") or 0)
        previous_cogs += cost * int(row.get("units_prev_30d") or 0)
        row["unit_cost"] = cost
        row["estimated_cogs_30d"] = round(cost * int(row.get("units_30d") or 0), 2)
        row["estimated_gross_margin_30d"] = round(float(row.get("net_sales_30d") or 0) - row["estimated_cogs_30d"], 2)

    for key, cogs, missing in (
        ("current_30d", current_cogs, missing_units_current),
        ("previous_30d", previous_cogs, missing_units_previous),
    ):
        a = order_summary[key]
        a["estimated_cogs"] = round(cogs, 2)
        a["cogs_missing_units"] = missing
        gm = float(a.get("net_product_sales") or 0) - cogs
        a["gross_margin"] = round(gm, 2)
        a["gross_margin_pct"] = (gm / float(a.get("net_product_sales") or 0)) if a.get("net_product_sales") else None
    return order_summary
