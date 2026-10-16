#!/bin/zsh
set -e

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Uso:"
  echo "  ./deploy/vps/SUBIR_DESDE_MAC.sh root@IP_DEL_VPS"
  exit 2
fi

PROJECT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE_STAGE="/tmp/sportland-smart-stage"
TMP_DUMP="/tmp/sportland_smart_vps_$$.backup"
cd "$PROJECT"

echo "1/4 — Pruebas"
python -m pytest -q

echo "2/4 — Dependencias para Linux"
python -m pip freeze \
  | grep -v -E '^(pyobjc|appnope|macholib|altgraph|modulegraph)=' \
  > deploy/vps/requirements-vps.txt

echo "3/4 — Copia de PostgreSQL"
pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --dbname=sportland_smart \
  --file="$TMP_DUMP"

echo "4/4 — Subiendo Sportland Smart"
ssh "$TARGET" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/database'"

rsync -az \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude '.env.portal' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'logs/' \
  --exclude 'backups/' \
  --exclude 'imports/amazon/reportes/*.csv' \
  "$PROJECT/" "$TARGET:$REMOTE_STAGE/"

scp "$TMP_DUMP" "$TARGET:$REMOTE_STAGE/database/sportland_smart.backup"
rm -f "$TMP_DUMP"

echo ""
echo "Carga completada."
echo "Ahora entra al VPS:"
echo "  ssh $TARGET"
echo ""
echo "Y ejecuta:"
echo "  sudo bash $REMOTE_STAGE/deploy/vps/INSTALAR_EN_CONTABO.sh smart.sportlandmx.com"
