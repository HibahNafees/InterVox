#!/bin/bash
# Daily MySQL dump from the compose stack; keeps the newest 14.
# cron (root on the devbox, since .env is root-only):
#   0 3 * * * /srv/intervox/deploy/backup.sh >> /var/log/intervox-backup.log 2>&1
# Oracle VM: 0 3 * * * $HOME/InterVox/deploy/backup.sh
set -euo pipefail
# Dumps hold user data: root-only files (600) in a root-only folder (700) (T-155).
umask 077
cd "$(dirname "$0")/.."
mkdir -p "$HOME/backups"
chmod 700 "$HOME/backups"
out="$HOME/backups/db-$(date +%F).sql.gz"
tmp="$out.partial"
# A failed dump must not replace a good backup or count towards the 14 kept.
if ! docker compose exec -T db sh -c 'mysqldump --single-transaction --no-tablespaces -u mock -p"$MYSQL_PASSWORD" mock_interviewer' \
  | gzip > "$tmp"; then
  rm -f "$tmp"
  echo "$(date -Is) backup FAILED" >&2
  exit 1
fi
mv "$tmp" "$out"
ls -1t "$HOME"/backups/db-*.sql.gz | tail -n +15 | xargs -r rm --
echo "$(date -Is) backup ok: $out ($(stat -c %s "$out") bytes)"
