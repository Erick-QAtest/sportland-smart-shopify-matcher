#!/bin/zsh
set -e

PROJECT="/Users/noecortes/Downloads/Sportland_Smart_x_Shopify_V1_1_AUTH_READY"
LOG_DIR="$PROJECT/logs"

mkdir -p "$LOG_DIR"
cd "$PROJECT"

source "$PROJECT/.venv/bin/activate"

echo "========================================"
echo "SPORTLAND DAILY START: $(date)"
echo "========================================"

echo "1/4 Smart × Shopify matcher"
python run_match.py

echo "2/4 Finanzas"
python run_finance.py

echo "3/4 Demand Intelligence"
python run_decisions_v21.py

echo "4/4 Behavior Intelligence"
python run_decisions_v23.py

echo "========================================"
echo "SPORTLAND DAILY OK: $(date)"
echo "========================================"
