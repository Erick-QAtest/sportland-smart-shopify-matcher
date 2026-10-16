#!/bin/bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecuta con sudo o como root."
  exit 2
fi

DOMAIN="${1:-}"
EMAIL="${2:-}"

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "Uso:"
  echo "  sudo bash deploy/vps/ACTIVAR_HTTPS.sh smart.sportlandmx.com correo@dominio.com"
  exit 2
fi

nginx -t

certbot --nginx \
  --non-interactive \
  --agree-tos \
  --redirect \
  --email "$EMAIL" \
  -d "$DOMAIN"

ENV_FILE="/opt/sportland-smart/.env.portal"

if grep -q '^SPORTLAND_COOKIE_SECURE=' "$ENV_FILE"; then
  sed -i 's/^SPORTLAND_COOKIE_SECURE=.*/SPORTLAND_COOKIE_SECURE=true/' "$ENV_FILE"
else
  echo 'SPORTLAND_COOKIE_SECURE=true' >> "$ENV_FILE"
fi

chown sportland:sportland "$ENV_FILE"
chmod 600 "$ENV_FILE"

systemctl restart sportland-smart.service
systemctl reload nginx

echo ""
echo "HTTPS activo:"
echo "  https://$DOMAIN"
