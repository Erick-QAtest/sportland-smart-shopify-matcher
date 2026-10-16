#!/bin/zsh
set -e

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Uso:"
  echo "  ./deploy/vps/DESPLEGAR_IMPACTO_7_1.sh lexradar@IP_DEL_VPS"
  exit 2
fi

PROJECT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT"

echo "1/3 — Validando"
python -m pytest -q

echo "2/3 — Actualizando código en VPS"
./deploy/vps/ACTUALIZAR_CODIGO_DESDE_MAC.sh "$TARGET"

echo "3/3 — Aplicando migración y reiniciando"
ssh "$TARGET" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo -u sportland \
  /opt/sportland-smart/.venv/bin/python \
  /opt/sportland-smart/run_impacto_setup.py
sudo systemctl restart sportland-smart.service
sleep 2
curl -fsS http://127.0.0.1:8700/salud >/dev/null
echo "Sportland Smart 7.1: OK"
REMOTE

echo ""
echo "Despliegue terminado."
echo "Abre:"
echo "  https://smart.sportlandmx.com/impacto"
