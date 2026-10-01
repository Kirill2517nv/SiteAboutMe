#!/usr/bin/env bash
# Ежедневный бэкап боевой базы на этот компьютер, хранится 10 последних.
# Запускается Планировщиком Windows через Git Bash (PowerShell 5.1 портит
# двоичный вывод при перенаправлении в файл).
#
# Дамп пишется во временный файл и становится настоящим только после проверки:
# оборванное соединение не должно вытеснить из ротации исправную копию.
set -euo pipefail

DEST="${BACKUP_DIR:-/c/Users/Kirill/Backups/site-db}"
KEEP=10
mkdir -p "$DEST"

out="$DEST/site-$(date +%Y-%m-%d_%H%M).dump"
tmp="$out.part"

# Реквизиты базы берутся из настроек Django на сервере – тот же источник, что у сайта,
# и пароль не покидает сервер. pg_dump только читает базу.
ssh -o BatchMode=yes -o ConnectTimeout=20 -p 2222 admin@192.168.1.199 \
  'cd /home/admin/site && venv/bin/python -c "
import os, django
os.environ.setdefault(\"DJANGO_SETTINGS_MODULE\", \"config.settings\")
django.setup()
from django.conf import settings
d = settings.DATABASES[\"default\"]
os.environ[\"PGPASSWORD\"] = d[\"PASSWORD\"]
os.execvp(\"pg_dump\", [\"pg_dump\", \"-Fc\", \"-h\", d[\"HOST\"] or \"localhost\",
          \"-p\", str(d[\"PORT\"] or 5432), \"-U\", d[\"USER\"], d[\"NAME\"]])
"' > "$tmp"

# Архив pg_dump -Fc начинается с сигнатуры PGDMP; пустой или текстовый файл – сбой.
if [ "$(head -c 5 "$tmp")" != "PGDMP" ]; then
  echo "$(date '+%F %T') FAIL: дамп не похож на pg_dump -Fc" >> "$DEST/backup.log"
  rm -f "$tmp"
  exit 1
fi
mv "$tmp" "$out"

# Ротация: оставить KEEP самых свежих.
ls -1t "$DEST"/site-*.dump | tail -n +$((KEEP + 1)) | xargs -r rm -f --
echo "$(date '+%F %T') OK $(basename "$out") $(stat -c %s "$out") bytes" >> "$DEST/backup.log"
