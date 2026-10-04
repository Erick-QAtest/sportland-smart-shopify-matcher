from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from smart_events.behavior import build_behavior, write_behavior_artifacts
from smart_events.decision_v22 import enhance_decisions, read_csv, write_csv
from smart_events.sheet_store import GoogleSheetEventStore, SheetConfig


def main() -> int:
    art = Path("artifacts")
    v21 = art / "smart_finance_decisions_v21.csv"
    if not v21.exists():
        if not Path("run_decisions_v21.py").exists():
            print("Falta run_decisions_v21.py / artifact v2.1")
            return 2
        rc = subprocess.call([sys.executable, "run_decisions_v21.py"])
        if rc:
            return rc

    cfg = SheetConfig.from_env()
    store = GoogleSheetEventStore(cfg)
    behavior = build_behavior(store.read_logged_events())
    write_behavior_artifacts(art, behavior)

    base = read_csv(v21)
    out = enhance_decisions(base, behavior["by_sku"])
    target = art / "smart_finance_decisions_v22.csv"
    write_csv(target, out)

    def count(a): return sum(1 for r in out if r.get("action") == a)
    print("Sportland Smart — Behavior-aware Decisions Sprint 2.2")
    print(f"Behavior signals with SKU: {len(behavior['by_sku'])}")
    print(f"Sell now: {count('VENDER_AHORA')}")
    print(f"Protect stock: {count('PROTEGER_STOCK')}")
    print(f"Liquidate variant: {count('LIQUIDAR_VARIANTE')}")
    print(f"Review variant: {count('REVISAR_VARIANTE')}")
    print(f"Artifact: {target}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
