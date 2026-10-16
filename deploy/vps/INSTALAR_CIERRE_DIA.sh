#!/usr/bin/env bash
# Activa el botón "Cerrar el día" del portal (unidad sportland-daily.path).
# Uso: sudo bash ~/sportland-src/deploy/vps/INSTALAR_CIERRE_DIA.sh
set -euo pipefail
SRC=/home/lexradar/sportland-src/deploy/vps
APP=/opt/sportland-smart
[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo."; exit 1; }
install -d -o sportland -g sportland -m 755 "$APP/logs/ops"
install -o root -g root -m 644 "$SRC/sportland-daily.path" /etc/systemd/system/sportland-daily.path
systemctl daemon-reload
systemctl enable --now sportland-daily.path
echo "cierre del día: $(systemctl is-active sportland-daily.path)"
