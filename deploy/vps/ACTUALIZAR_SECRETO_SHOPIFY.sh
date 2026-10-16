#!/usr/bin/env bash
# Pide el secreto de Shopify (oculto), lo prueba contra Shopify y solo si funciona lo guarda
# en /opt/sportland-smart/.env. Opcionalmente relanza el pipeline diario.
# Uso: sudo bash ~/sportland-src/deploy/vps/ACTUALIZAR_SECRETO_SHOPIFY.sh [--relanzar]
# Si existe /home/lexradar/.shopify_secret (copiado desde la Mac) lo usa y lo borra; si no, lo pide.
set -euo pipefail
APP=/opt/sportland-smart
[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo."; exit 1; }

SECRET_FILE=/home/lexradar/.shopify_secret
if [ -f "$SECRET_FILE" ]; then
  SECRET=$(tr -d '[:space:]"'"'"'' < "$SECRET_FILE")
  shred -u "$SECRET_FILE" 2>/dev/null || rm -f "$SECRET_FILE"
  echo "Secreto tomado del archivo copiado desde la Mac (archivo borrado)."
else
  read -rsp "SHOPIFY_CLIENT_SECRET (no se verá al escribir): " SECRET; echo
  SECRET=$(printf '%s' "$SECRET" | tr -d '[:space:]')
fi
[ -n "$SECRET" ] || { echo "Vacío; no se cambió nada."; exit 1; }

echo "==> Probando contra Shopify (sin guardar todavía)"
if ! printf '%s' "$SECRET" | runuser -u sportland -- bash -c "cd $APP && .venv/bin/python -c '
import sys
from dataclasses import replace
from sportland_matcher.config import load_config
from sportland_matcher.shopify_source import acquire_shopify_auth
cfg = load_config(\".env\")
cfg = replace(cfg, shopify_client_secret=sys.stdin.read(), shopify_token=\"\")
auth = acquire_shopify_auth(cfg)
print(\"Shopify OK, modo:\", auth.mode)
'"; then
  echo "Shopify rechazó el secreto; no se cambió nada. Revisa que sea el de la misma app que SHOPIFY_CLIENT_ID."
  exit 1
fi

echo "==> Guardando en $APP/.env"
printf '%s' "$SECRET" | python3 -c '
import re, sys
path = "/opt/sportland-smart/.env"
value = sys.stdin.read()
text = open(path).read()
if re.search(r"(?m)^SHOPIFY_CLIENT_SECRET=", text):
    text = re.sub(r"(?m)^SHOPIFY_CLIENT_SECRET=.*$", lambda m: "SHOPIFY_CLIENT_SECRET=" + value, text)
else:
    text += "\nSHOPIFY_CLIENT_SECRET=" + value + "\n"
open(path, "w").write(text)
'
unset SECRET
chown sportland:sportland "$APP/.env" && chmod 600 "$APP/.env"

again=n
if [ "${1:-}" = "--relanzar" ]; then again=s; else read -rp "¿Relanzar ahora la corrida de prueba del pipeline? [s/N] " again; fi
if [[ "$again" =~ ^[sS]$ ]]; then
  systemctl start --no-block sportland-daily.service
  echo "Corriendo en segundo plano. Avance: tail -f $APP/logs/daily.log"
fi
