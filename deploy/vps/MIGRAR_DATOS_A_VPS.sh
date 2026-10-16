#!/usr/bin/env bash
# Reemplaza la base del VPS con la copia de la Mac, conservando los registros de Impacto
# que solo existen en el VPS. Uso (en el VPS, como lexradar):
#   sudo bash ~/sportland-src/deploy/vps/MIGRAR_DATOS_A_VPS.sh
set -euo pipefail

DB=sportland_smart
SRC_BACKUP="/home/lexradar/sportland_smart_mac.backup"
BACKUP_DIR=/var/backups/sportland
TS=$(date +%Y%m%d_%H%M)
q() { runuser -u sportland -- psql -At "$DB" -c "$1"; }

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo."; exit 1; }
[ -f "$SRC_BACKUP" ] || { echo "No encuentro $SRC_BACKUP (la copia de la Mac)."; exit 1; }

portal_events=$(q "select count(*) from customer_events where source = 'sportland_portal'")
if [ "$portal_events" != "0" ]; then
  echo "ALTO: hay $portal_events eventos capturados en el portal del VPS. No se migró nada."
  exit 3
fi

echo "==> Respaldo completo de la base actual del VPS"
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
runuser -u sportland -- pg_dump -Fc "$DB" > "$BACKUP_DIR/vps_antes_de_migrar_$TS.backup"
runuser -u sportland -- pg_dump --data-only -t recommendation_episodes -t recommendation_impact_audit "$DB" \
  > "$BACKUP_DIR/impacto_vps_$TS.sql"
echo "    impacto a conservar: $(q 'select count(*) from recommendation_impact_audit') registros"

echo "==> Restaurando la copia de la Mac"
install -o sportland -g sportland -m 600 "$SRC_BACKUP" /tmp/sportland_smart_mac.backup
systemctl stop sportland-smart
runuser -u sportland -- pg_restore --clean --if-exists --no-owner --no-privileges --dbname="$DB" /tmp/sportland_smart_mac.backup

echo "==> Reponiendo los registros de Impacto del VPS"
runuser -u sportland -- psql -q -v ON_ERROR_STOP=1 "$DB" < "$BACKUP_DIR/impacto_vps_$TS.sql"

rm -f /tmp/sportland_smart_mac.backup "$SRC_BACKUP"
systemctl start sportland-smart
sleep 2
curl -fsS http://127.0.0.1:8700/salud >/dev/null && echo "portal: OK"
echo "eventos: $(q 'select count(*) from customer_events')  clientes: $(q 'select count(*) from customers')  impacto: $(q 'select count(*) from recommendation_impact_audit')"
echo "Respaldo previo en $BACKUP_DIR/vps_antes_de_migrar_$TS.backup"
