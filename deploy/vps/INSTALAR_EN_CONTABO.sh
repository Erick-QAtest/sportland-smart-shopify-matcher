#!/bin/bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecuta este script con sudo o como root."
  exit 2
fi

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Uso:"
  echo "  sudo bash deploy/vps/INSTALAR_EN_CONTABO.sh smart.sportlandmx.com"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="/opt/sportland-smart"
DB_DUMP="$SOURCE_ROOT/database/sportland_smart.backup"

echo ""
echo "Sportland Smart 7.0 — instalación en VPS"
echo "Dominio: $DOMAIN"
echo ""

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  python3 python3-venv python3-pip \
  postgresql postgresql-client \
  nginx certbot python3-certbot-nginx \
  rsync curl

if ! id sportland >/dev/null 2>&1; then
  useradd \
    --system \
    --home /var/lib/sportland \
    --create-home \
    --shell /usr/sbin/nologin \
    sportland
fi

mkdir -p "$TARGET"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude '.env.portal' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'database/sportland_smart.backup' \
  "$SOURCE_ROOT/" "$TARGET/"
chown -R sportland:sportland "$TARGET"

if ! runuser -u postgres -- psql -tAc \
  "SELECT 1 FROM pg_roles WHERE rolname='sportland'" | grep -q 1; then
  runuser -u postgres -- createuser \
    --no-superuser --no-createdb --no-createrole sportland
fi

if ! runuser -u postgres -- psql -tAc \
  "SELECT 1 FROM pg_database WHERE datname='sportland_smart'" | grep -q 1; then
  runuser -u postgres -- createdb --owner=sportland sportland_smart
fi

if [[ -f "$DB_DUMP" ]]; then
  echo "Restaurando PostgreSQL..."
  cp "$DB_DUMP" /tmp/sportland_smart.restore.backup
  chown sportland:sportland /tmp/sportland_smart.restore.backup
  runuser -u sportland -- pg_restore \
    --clean --if-exists --no-owner --no-privileges \
    --dbname=sportland_smart \
    /tmp/sportland_smart.restore.backup
  rm -f /tmp/sportland_smart.restore.backup
else
  echo "ADVERTENCIA: no se encontró database/sportland_smart.backup."
fi

cat > "$TARGET/.env" <<'EOF'
DATABASE_URL=postgresql:///sportland_smart
MEMORY_SOURCE_NAME=sportland_smart_v5
MEMORY_STORE_PHONE=true
EOF
chown sportland:sportland "$TARGET/.env"
chmod 600 "$TARGET/.env"

runuser -u sportland -- python3 -m venv "$TARGET/.venv"
runuser -u sportland -- "$TARGET/.venv/bin/python" -m pip install --upgrade pip wheel

if [[ -f "$TARGET/deploy/vps/requirements-vps.txt" ]]; then
  runuser -u sportland -- "$TARGET/.venv/bin/pip" install \
    -r "$TARGET/deploy/vps/requirements-vps.txt"
elif [[ -f "$TARGET/requirements.txt" ]]; then
  runuser -u sportland -- "$TARGET/.venv/bin/pip" install \
    -r "$TARGET/requirements.txt"
else
  runuser -u sportland -- "$TARGET/.venv/bin/pip" install \
    python-dotenv "psycopg[binary]"
fi

echo ""
echo "Configura ahora el acceso del administrador."
echo "La contraseña se pedirá de forma oculta."
echo ""

runuser -u sportland -- "$TARGET/.venv/bin/python" \
  "$TARGET/configurar_acceso_admin.py" \
  --archivo "$TARGET/.env.portal" \
  --dominio "$DOMAIN" \
  --cookie-segura no

chmod 600 "$TARGET/.env.portal"

cp "$TARGET/deploy/vps/sportland-smart.service" \
  /etc/systemd/system/sportland-smart.service

cp "$TARGET/deploy/vps/backup_postgres.sh" \
  /usr/local/sbin/sportland-smart-backup
chmod 750 /usr/local/sbin/sportland-smart-backup

cp "$TARGET/deploy/vps/sportland-backup.service" \
  /etc/systemd/system/sportland-backup.service
cp "$TARGET/deploy/vps/sportland-backup.timer" \
  /etc/systemd/system/sportland-backup.timer

NGINX_FILE="/etc/nginx/sites-available/sportland-smart"
sed "s/__SPORTLAND_DOMAIN__/$DOMAIN/g" \
  "$TARGET/deploy/vps/nginx-sportland-smart.conf.template" \
  > "$NGINX_FILE"

ln -sfn "$NGINX_FILE" /etc/nginx/sites-enabled/sportland-smart

nginx -t
systemctl reload nginx

systemctl daemon-reload
systemctl enable --now sportland-smart.service
systemctl enable --now sportland-backup.timer

sleep 2

if curl -fsS http://127.0.0.1:8700/salud >/dev/null; then
  echo ""
  echo "Portal interno: OK"
else
  echo ""
  echo "ERROR: el portal no respondió."
  echo "Revisa:"
  echo "  journalctl -u sportland-smart -n 100 --no-pager"
  exit 3
fi

echo ""
echo "Instalación base completada."
echo "Antes de compartir el portal:"
echo "1. Haz que $DOMAIN apunte a este VPS."
echo "2. Activa HTTPS:"
echo ""
echo "   sudo bash $TARGET/deploy/vps/ACTIVAR_HTTPS.sh $DOMAIN TU_CORREO"
echo ""
