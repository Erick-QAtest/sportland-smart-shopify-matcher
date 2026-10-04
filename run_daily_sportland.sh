#!/bin/zsh
set -uo pipefail

PROJECT="/Users/noecortes/Downloads/Sportland_Smart_x_Shopify_V1_1_AUTH_READY"
LOG_DIR="$PROJECT/logs"

mkdir -p "$LOG_DIR"
cd "$PROJECT"

source "$PROJECT/.venv/bin/activate"

python run_ops_status.py start || true

run_step() {
  local label="$1"
  shift

  echo ""
  echo "========================================"
  echo "$label"
  echo "========================================"

  python run_ops_status.py step --name "$label" || true

  if "$@"; then
    return 0
  else
    local code=$?
    echo "SPORTLAND DAILY FAILED: $label (exit=$code)"
    python run_ops_status.py fail --step "$label" --exit-code "$code" || true
    python run_ops_alert.py --step "$label" --exit-code "$code" || true
    python run_ops_health.py || true
    exit "$code"
  fi
}

echo "========================================"
echo "SPORTLAND DAILY START: $(date)"
echo "========================================"

run_step "1/6 Memory Orchestrator" python run_memory_daily.py
run_step "2/6 Finanzas" python run_finance.py
run_step "3/6 Demand Intelligence" python run_decisions_v21.py
run_step "4/6 Behavior Intelligence" python run_decisions_v23.py
run_step "5/6 PostgreSQL Backup" python run_ops_backup.py
run_step "6/6 Ops Health" python run_ops_health.py

python run_ops_status.py ok || true
python run_ops_health.py || true

echo "========================================"
echo "SPORTLAND DAILY OK: $(date)"
echo "========================================"
