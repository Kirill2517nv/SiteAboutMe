#!/usr/bin/env bash
# Выкатка версии из origin/main на оба сервера. Запуск с dev: bash scripts/deploy.sh
# lbm-srv (основной) – полный деплой; ноутбук (реплика, запасной) – код и статика
# без migrate: схема приходит репликой, а запись в реплику невозможна.
set -euo pipefail
LBM="ssh -o BatchMode=yes lih@lbm-srv"
LAPTOP="ssh -o BatchMode=yes -p 2222 admin@192.168.1.199"

# После failover основной стал ноутбук – эта схема выкатки к нему не подходит.
if $LAPTOP 'test -e /home/admin/site/.failover'; then
  echo "Ноутбук в режиме аварии (.failover) – выкатка отменена, см. docs/two-servers.md"
  exit 1
fi

echo "== lbm-srv"
$LBM 'set -e; cd ~/siteSchool
git pull --ff-only
venv/bin/pip install -q -r requirements.txt
venv/bin/python manage.py migrate --noinput
venv/bin/python manage.py collectstatic --noinput
docker build -q -t site-sandbox-cpp docker/sandbox-cpp >/dev/null
sudo systemctl restart siteschool-web siteschool-daphne siteschool-celery siteschool-celerybeat
git log -1 --oneline'

echo "== ноутбук"
$LAPTOP 'set -e; cd ~/site
git pull --ff-only
venv/bin/pip install -q -r requirements.txt
venv/bin/python manage.py collectstatic --noinput
docker build -q -t site-sandbox-cpp docker/sandbox-cpp >/dev/null
git log -1 --oneline'
