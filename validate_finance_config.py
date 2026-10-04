from __future__ import annotations

from dotenv import load_dotenv

from smart_finance.config import FinanceConfig


def main() -> int:
    load_dotenv(".env")
    cfg = FinanceConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR")
        for e in errors:
            print(f"- {e}")
        return 2
    print("OK — finance config is valid and read-only")
    print(f"Schema: {cfg.schema}")
    print(f"Spreadsheet: {cfg.spreadsheet_id}")
    if cfg.schema == "v2":
        print(f"Debts sheet: {cfg.debts_sheet}")
        print(f"Payments sheet: {cfg.payments_sheet}")
        print(f"Cash sheet: {cfg.cashflow_sheet}")
    else:
        print(f"Providers sheet: {cfg.providers_sheet}")
        print(f"Payments sheet: {cfg.payments_sheet}")
        print(f"Cashflow sheet: {cfg.cashflow_sheet}")
    print(f"Matches CSV: {cfg.matches_csv}")
    print(f"Artifacts: {cfg.artifacts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
