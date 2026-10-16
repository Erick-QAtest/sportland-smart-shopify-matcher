#!/usr/bin/env bash
# Actualiza el código de /opt/sportland-smart con lo subido a ~/sportland-src.
# Respalda el código actual, no toca .env/logs/datos/respaldos, aplica migraciones,
# corre las pruebas y reinicia el portal.
# Uso: sudo bash ~/sportland-src/deploy/vps/ACTUALIZAR_CODIGO.sh
set -euo pipefail
SRC=/home/lexradar/sportland-src
APP=/opt/sportland-smart
BK=/var/backups/sportland
TS=$(date +%Y%m%d_%H%M)
[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo."; exit 1; }
[ -f "$SRC/run_sportland_portal.py" ] || { echo "No encuentro el código en $SRC"; exit 1; }

EXCLUDES=(--exclude '.env' --exclude '.env.*' --exclude '.venv/' --exclude '.git/' --exclude '__pycache__/'
          --exclude '.pytest_cache/' --exclude 'logs/' --exclude 'artifacts/' --exclude 'backups/'
          --exclude 'imports/' --exclude 'eventos_log.csv' --exclude '*.zip' --exclude 'Sportland_Smart_*/')

echo "==> Respaldo del código actual"
install -d -m 700 "$BK"
tar -C "$APP" -czf "$BK/codigo_antes_$TS.tgz" --exclude=.venv --exclude=logs --exclude=artifacts --exclude=backups --exclude=imports --exclude='.env*' .

echo "==> Copiando código nuevo"
rsync -a "${EXCLUDES[@]}" "$SRC/" "$APP/"
chown -R sportland:sportland "$APP"

echo "==> Migraciones"
runuser -u sportland -- bash -c "cd $APP && .venv/bin/python -c '
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations
import psycopg
from psycopg.rows import dict_row
conn = psycopg.connect(MemoryConfig.from_env().database_url, row_factory=dict_row, autocommit=True)
print(\"aplicadas:\", apply_migrations(conn) or \"ninguna nueva\")
'"

echo "==> Pruebas"
if ! runuser -u sportland -- bash -c "cd $APP && .venv/bin/python -m pytest -q | tail -1"; then
  echo "Las pruebas fallaron. El portal NO se reinició (sigue con la versión anterior en memoria)."
  echo "Para volver al código anterior: tar -C $APP -xzf $BK/codigo_antes_$TS.tgz"
  exit 1
fi

echo "==> Reiniciando el portal"
systemctl restart sportland-smart
sleep 2
curl -fsS http://127.0.0.1:8700/salud >/dev/null && echo "portal: OK"
echo "Respaldo del código anterior: $BK/codigo_antes_$TS.tgz"
