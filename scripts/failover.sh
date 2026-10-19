#!/usr/bin/env bash
# Авария: lbm-srv недоступен – сайт поднимается на ноутбуке.
# Запуск на ноутбуке: sudo bash /home/admin/site/scripts/failover.sh
# После promote реплики больше нет: возврат на lbm-srv и пересборка реплики –
# отдельная процедура, docs/two-servers.md.
set -euo pipefail
SITE=/home/admin/site
LBM=100.65.27.51

[ "$(id -u)" = 0 ] || { echo "Запускать через sudo"; exit 1; }

# Две основные базы и два Celery Beat хуже простоя: пока основная на lbm-srv
# отвечает, аварии нет – сначала остановить сайт там.
if pg_isready -q -h "$LBM" -p 5433 -t 5; then
  echo "PostgreSQL на lbm-srv отвечает. Остановите там siteschool-* и postgresql@16-siteschool"
  echo "или запустите с --force, если lbm-srv точно не обслуживает учеников."
  [ "${1:-}" = "--force" ] || exit 1
fi
read -rp "Поднять сайт на ноутбуке (promote реплики, необратимо)? [yes/N] " answer
[ "$answer" = yes ] || exit 1

touch "$SITE/.failover"   # cron media и deploy.sh видят флаг и ноутбук не трогают

pg_ctlcluster 16 main promote
until [ "$(sudo -u postgres psql -tAc 'select pg_is_in_recovery()')" = f ]; do sleep 1; done

systemctl enable --now site daphne celery celerybeat
ln -sfn ../sites-available/site-local /etc/nginx/sites-enabled/site
nginx -t && systemctl reload nginx

echo "Сайт работает на ноутбуке. Возврат на lbm-srv – docs/two-servers.md"
