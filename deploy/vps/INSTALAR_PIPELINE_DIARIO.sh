#!/usr/bin/env bash
# Programa el pipeline diario en el VPS y lanza una corrida de prueba.
# Uso: sudo bash ~/sportland-src/deploy/vps/INSTALAR_PIPELINE_DIARIO.sh
set -euo pipefail
SRC=/home/lexradar/sportland-src/deploy/vps
APP=/opt/sportland-smart
[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo."; exit 1; }

install -d -o sportland -g sportland -m 755 "$APP/logs"
touch "$APP/logs/daily.log" && chown sportland:sportland "$APP/logs/daily.log" && chmod 644 "$APP/logs/daily.log"
install -o root -g root -m 644 "$SRC/sportland-daily.service" /etc/systemd/system/sportland-daily.service
install -o root -g root -m 644 "$SRC/sportland-daily.timer" /etc/systemd/system/sportland-daily.timer
systemctl daemon-reload
systemctl enable --now sportland-daily.timer
systemctl list-timers sportland-daily.timer --no-pager | head -3

echo "==> Corrida de prueba en segundo plano (tarda de 20 a 60 minutos)"
systemctl start --no-block sportland-daily.service
echo "Sigue el avance con: tail -f $APP/logs/daily.log"
