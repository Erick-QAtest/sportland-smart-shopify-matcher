#!/bin/bash
set -euo pipefail

DEST="/var/backups/sportland-smart"
mkdir -p "$DEST"
chown sportland:sportland "$DEST"

STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$DEST/sportland_smart_${STAMP}.backup"

runuser -u sportland -- pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --dbname=sportland_smart \
  --file="$FILE"

chown sportland:sportland "$FILE"
chmod 600 "$FILE"
find "$DEST" -type f -name 'sportland_smart_*.backup' -mtime +14 -delete
