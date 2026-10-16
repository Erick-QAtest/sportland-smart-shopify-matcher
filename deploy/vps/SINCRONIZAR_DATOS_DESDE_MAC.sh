#!/bin/zsh
set -e

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Uso:"
  echo "  ./deploy/vps/SINCRONIZAR_DATOS_DESDE_MAC.sh root@IP_DEL_VPS"
  exit 2
fi

PROJECT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="/tmp/sportland_smart_sync_$$.backup"
cd "$PROJECT"

echo "Creando copia de PostgreSQL..."
pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --dbname=sportland_smart \
  --file="$TMP"

echo "Subiendo por SSH..."
scp "$TMP" "$TARGET:/tmp/sportland_smart_sync.backup"
rm -f "$TMP"

ssh "$TARGET" 'bash -s' <<'REMOTE'
set -euo pipefail
chown sportland:sportland /tmp/sportland_smart_sync.backup
systemctl stop sportland-smart.service
runuser -u sportland -- pg_restore \
  --clean --if-exists --no-owner --no-privileges \
  --dbname=sportland_smart \
  /tmp/sportland_smart_sync.backup
rm -f /tmp/sportland_smart_sync.backup
systemctl start sportland-smart.service
sleep 2
curl -fsS http://127.0.0.1:8700/salud >/dev/null
echo "Sincronización terminada."
REMOTE
