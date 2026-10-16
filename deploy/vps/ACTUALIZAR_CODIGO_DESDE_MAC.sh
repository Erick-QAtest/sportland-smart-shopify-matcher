#!/bin/zsh
set -e

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Uso:"
  echo "  ./deploy/vps/ACTUALIZAR_CODIGO_DESDE_MAC.sh root@IP_DEL_VPS"
  exit 2
fi

PROJECT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="/tmp/sportland-smart-code-update"

cd "$PROJECT"
python -m pytest -q

ssh "$TARGET" "rm -rf '$STAGE' && mkdir -p '$STAGE'"

rsync -az \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude '.env.portal' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'logs/' \
  --exclude 'backups/' \
  --exclude 'database/sportland_smart.backup' \
  --exclude 'imports/amazon/reportes/*.csv' \
  "$PROJECT/" "$TARGET:$STAGE/"

ssh "$TARGET" 'bash -s' <<'REMOTE'
set -euo pipefail
rsync -a \
  --exclude '.env' \
  --exclude '.env.portal' \
  --exclude '.venv/' \
  /tmp/sportland-smart-code-update/ /opt/sportland-smart/
chown -R sportland:sportland /opt/sportland-smart
if [[ -f /opt/sportland-smart/deploy/vps/requirements-vps.txt ]]; then
  runuser -u sportland -- /opt/sportland-smart/.venv/bin/pip install \
    -r /opt/sportland-smart/deploy/vps/requirements-vps.txt
fi
systemctl restart sportland-smart.service
sleep 2
curl -fsS http://127.0.0.1:8700/salud >/dev/null
rm -rf /tmp/sportland-smart-code-update
echo "Código actualizado."
REMOTE
