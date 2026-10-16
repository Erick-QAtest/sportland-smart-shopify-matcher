#!/usr/bin/env bash
# Deja el VPS listo para correr el pipeline diario: llave de Google, configuración de
# Sheets/Shopify/finanzas y dependencias. Los secretos de Shopify se piden ocultos.
# Uso (en el VPS, como lexradar), después de subir la llave de Google a ~/google-service-account.json:
#   sudo bash ~/sportland-src/deploy/vps/INSTALAR_CONFIG_PIPELINE.sh
set -euo pipefail

APP=/opt/sportland-smart
HOME_DIR=/home/lexradar
CONFIG="$HOME_DIR/env.pipeline"
KEY_SRC="$HOME_DIR/google-service-account.json"
KEY_DIR=/etc/sportland-smart
MIRROR=/var/backups/sportland-espejo
TS=$(date +%Y%m%d_%H%M)

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo."; exit 1; }
[ -f "$CONFIG" ] || { echo "Falta $CONFIG (configuración generada desde la Mac)."; exit 1; }
[ -f "$KEY_SRC" ] || [ -f "$KEY_DIR/google-service-account.json" ] || { echo "Falta la llave de Google en $KEY_SRC."; exit 1; }

echo "==> Llave de Google en $KEY_DIR (solo root y sportland pueden leerla)"
install -d -o root -g sportland -m 750 "$KEY_DIR"
if [ -f "$KEY_SRC" ]; then
  install -o root -g sportland -m 640 "$KEY_SRC" "$KEY_DIR/google-service-account.json"
  shred -u "$KEY_SRC" 2>/dev/null || rm -f "$KEY_SRC"
fi

echo "==> Carpeta espejo de respaldos: $MIRROR"
install -d -o sportland -g sportland -m 700 "$MIRROR"

echo "==> Respaldo de la configuración actual"
install -d -o root -g root -m 700 /root/sportland-env-backups
install -o root -g root -m 600 "$APP/.env" "/root/sportland-env-backups/.env.antes_pipeline_$TS"

current() { sed -nE "s/^$1=//p" "$APP/.env" | head -1; }
SHOP_ID=$(current SHOPIFY_CLIENT_ID)
SHOP_SECRET=$(current SHOPIFY_CLIENT_SECRET)
if [ -z "$SHOP_ID" ]; then read -rp "SHOPIFY_CLIENT_ID: " SHOP_ID; fi
if [ -z "$SHOP_SECRET" ]; then read -rsp "SHOPIFY_CLIENT_SECRET (no se verá al escribir): " SHOP_SECRET; echo; fi
[ -n "$SHOP_ID" ] && [ -n "$SHOP_SECRET" ] || { echo "Faltan las credenciales de Shopify; no se cambió nada."; exit 1; }

echo "==> Nueva .env (base de datos y memoria se conservan)"
NEW=$(mktemp)
grep -E '^(DATABASE_URL|MEMORY_SOURCE_NAME)=' "$APP/.env" > "$NEW"
echo "MEMORY_STORE_PHONE=true" >> "$NEW"
grep -vE '^(#|$|DATABASE_URL=|MEMORY_)' "$CONFIG" >> "$NEW"
printf 'SHOPIFY_CLIENT_ID=%s\nSHOPIFY_CLIENT_SECRET=%s\n' "$SHOP_ID" "$SHOP_SECRET" >> "$NEW"
install -o sportland -g sportland -m 600 "$NEW" "$APP/.env"
rm -f "$NEW" "$CONFIG"
unset SHOP_SECRET

echo "==> Dependencias de Python"
runuser -u sportland -- bash -c "cd $APP && .venv/bin/pip install -q -r requirements.txt -r requirements-memory.txt -r requirements-finance.txt"

echo "==> Validación (lee Sheets y Shopify, no escribe nada)"
runuser -u sportland -- bash -c "cd $APP && .venv/bin/python validate_config.py && .venv/bin/python validate_finance_config.py"
echo "Listo. Respaldo de la configuración anterior en /root/sportland-env-backups/.env.antes_pipeline_$TS"
