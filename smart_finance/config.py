from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FinanceConfig:
    source: str = "sheets"
    schema: str = "legacy"
    spreadsheet_id: str = ""
    service_account_file: str = ""
    inventory_sheet: str = "Inventario"
    providers_sheet: str = "Proveedores"
    payments_sheet: str = "Proyeccion de pagos"
    cashflow_sheet: str = "Flujo de caja"
    debts_sheet: str = "Deudas"
    expenses_sheet: str = "Gastos externos"
    artifacts_dir: str = "artifacts"
    matches_csv: str = "artifacts/demand_supply_matches.csv"
    reserve_cash: float = 0.0
    horizon_days: int = 30
    manual_debts: list[dict[str, Any]] = field(default_factory=list)
    shopify_first: bool = True
    spreadsheet_cost_fallback: bool = True

    @classmethod
    def from_env(cls) -> "FinanceConfig":
        cfg = cls(
            source=os.getenv("FINANCE_SOURCE", "sheets").strip().lower(),
            schema=os.getenv("FINANCE_SCHEMA", "legacy").strip().lower(),
            spreadsheet_id=os.getenv("FINANCE_SPREADSHEET_ID", "").strip(),
            service_account_file=os.getenv(
                "FINANCE_GOOGLE_SERVICE_ACCOUNT_FILE",
                os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
            ).strip(),
            inventory_sheet=os.getenv("FINANCE_INVENTORY_SHEET", "Inventario"),
            providers_sheet=os.getenv("FINANCE_PROVIDERS_SHEET", "Proveedores"),
            payments_sheet=os.getenv("FINANCE_PAYMENTS_SHEET", "Proyeccion de pagos"),
            cashflow_sheet=os.getenv("FINANCE_CASHFLOW_SHEET", "Flujo de caja"),
            debts_sheet=os.getenv("FINANCE_DEBTS_SHEET", "Deudas"),
            expenses_sheet=os.getenv("FINANCE_EXPENSES_SHEET", "Gastos externos"),
            artifacts_dir=os.getenv("FINANCE_ARTIFACTS_DIR", "artifacts"),
            matches_csv=os.getenv("FINANCE_MATCHES_CSV", "artifacts/demand_supply_matches.csv"),
            reserve_cash=float(os.getenv("FINANCE_RESERVE_CASH", "0") or 0),
            horizon_days=int(os.getenv("FINANCE_HORIZON_DAYS", "30") or 30),
            shopify_first=os.getenv("FINANCE_SHOPIFY_FIRST", "true").strip().lower() not in {"0", "false", "no"},
            spreadsheet_cost_fallback=os.getenv("FINANCE_SPREADSHEET_COST_FALLBACK", "true").strip().lower() not in {"0", "false", "no"},
        )
        rules = os.getenv("FINANCE_RULES_FILE", "finance_rules.json")
        p = Path(rules)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            cfg.manual_debts = data.get("manual_debts", [])
            if "reserve_cash" in data:
                cfg.reserve_cash = float(data["reserve_cash"] or 0)
        return cfg

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.schema not in {"legacy", "v2"}:
            errors.append("FINANCE_SCHEMA must be 'legacy' or 'v2'")
        if self.source == "sheets":
            if not self.spreadsheet_id:
                errors.append("FINANCE_SPREADSHEET_ID is required when FINANCE_SOURCE=sheets")
            if not self.service_account_file:
                errors.append("GOOGLE_SERVICE_ACCOUNT_FILE/FINANCE_GOOGLE_SERVICE_ACCOUNT_FILE is required")
            elif not Path(self.service_account_file).exists():
                errors.append(f"Service Account file not found: {self.service_account_file}")
        elif self.source != "fixture":
            errors.append("FINANCE_SOURCE must be 'sheets' or 'fixture'")
        return errors
