# Два сервера

Прод переехал: основной сервер теперь lbm-srv, а бывший прод (ноутбук) остался
шлюзом и запасным. Этот документ – для учителя и единственного админа: что где
живёт, как выкатывать версию, как проверять реплику и что делать при аварии.

## Схема

```text
интернет
   │
   ▼
роутер
   │
   ▼
ноутбук – nginx + Let's Encrypt (kirill-lab.ru)
   │  Tailscale
   ▼
lbm-srv – nginx (100.65.27.51:80)
   │
   ├── /run/siteschool/web.sock     → siteschool-web (Gunicorn, 9 воркеров)
   ├── /run/siteschool/daphne.sock  → siteschool-daphne (WebSocket)
   ├── /static/ и /media/
   ├── PostgreSQL 16/siteschool, порт 5433
   ├── Redis localhost:6379, базы 1 и 2
   └── Docker: python:3.11-slim и site-sandbox-cpp
```

Снаружи сайт виден только через ноутбук: на нём сертификат Let's Encrypt, туда
приходит трафик из интернета. lbm-srv слушает свой Tailscale-адрес и в интернет
не смотрит. nginx на lbm-srv берёт настоящий IP ученика из `X-Forwarded-For`
шлюза (`set_real_ip_from 100.64.0.0/10`) и передаёт Django `X-Forwarded-Proto`
шлюза (`https`), а не свой `$scheme` – иначе сломались бы CSRF и редиректы.

## Что где

| | lbm-srv – основной | ноутбук – шлюз и запасной |
|---|---|---|
| **Роль** | Сайт, база, Celery, песочница | TLS и вход из интернета; запасной сайт после аварии |
| **Вход** | `ssh lih@lbm-srv`, Tailscale 100.65.27.51, sudo без пароля | `ssh admin@192.168.1.199 -p 2222`, sudo требует пароль |
| **Проект** | `/home/lih/siteSchool`, пользователь lih | `/home/admin/site`, пользователь admin |
| **Юниты** | `siteschool-web`, `siteschool-daphne`, `siteschool-celery`, `siteschool-celerybeat` | `site`, `daphne`, `celery`, `celerybeat` – в обычном режиме остановлены и выключены (`disable`); работает `redis-server` |
| **Сокеты** | `/run/siteschool/web.sock`, `/run/siteschool/daphne.sock`; каталог создаёт `/etc/tmpfiles.d/siteschool.conf` | `/run/gunicorn/site.sock`, `/run/daphne/site.sock` – нужны только после `failover.sh` |
| **PostgreSQL** | Отдельный кластер `16/siteschool`, порт 5433, база и роль `siteschool` | Streaming-реплика кластера `16/siteschool` в `16/main`, порт 5432 |
| **Redis** | Общий `redis-server`, localhost:6379; базы 1 (Celery: `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`) и 2 (Channels: `CHANNELS_REDIS_URL`) | Свой `redis-server`; нужен только после аварии |
| **Celery Beat** | Работает только здесь | Выключен до аварии |
| **media** | Источник: `/home/lih/siteSchool/media/` | Копия: крон пользователя admin тянет её каждые 10 минут |
| **nginx** | `/etc/nginx/sites-available/siteschool` (`deploy/nginx-lbm-srv.conf`), слушает 100.65.27.51:80 | `/etc/nginx/sites-available/site` – шлюз (`deploy/nginx-gateway.conf`); аварийный `/etc/nginx/sites-available/site-local` (`deploy/nginx-local.conf`) |

Репликация и media на ноутбуке держатся на двух вещах. Реплику настраивает
`/var/lib/postgresql/.pgpass` (строка
`100.65.27.51:5433:replication:siteschool_replica:<пароль>`, права 600, владелец
postgres). Media тянет крон:

```bash
*/10 * * * * [ -e /home/admin/site/.failover ] || rsync -a lih@100.65.27.51:/home/lih/siteSchool/media/ /home/admin/site/media/ 2>>/home/admin/site/media-sync.log
```

Флаг `/home/admin/site/.failover` ставит `failover.sh`; пока он есть, крон media
и `deploy.sh` ноутбук не трогают.

На lbm-srv postgres и nginx при загрузке стартуют раньше, чем Tailscale выдаст
адрес. Чтобы они всё равно слушали его, в
`/etc/sysctl.d/60-siteschool-nonlocal-bind.conf` стоит
`net.ipv4.ip_nonlocal_bind=1`.

## Имена siteschool и почему

На lbm-srv позже будут другие сайты, поэтому всё школьного сайта называется с
префиксом `siteschool`: юниты `siteschool-web` (Gunicorn, 9 воркеров),
`siteschool-daphne`, `siteschool-celery` (12 процессов, очереди
`code_execution,default`), `siteschool-celerybeat`; сокеты в `/run/siteschool/`;
nginx `/etc/nginx/sites-available/siteschool`; логи nginx
`/var/log/nginx/siteschool.access.log` и `siteschool.error.log`. Логи сервисов –
`journalctl -u siteschool-web` и так же для остальных.

PostgreSQL – отдельный кластер `16/siteschool` на порту 5433 (юнит
`postgresql@16-siteschool`), а не общий `16/main`. Причина: физическая реплика
копирует кластер целиком, и базы будущих сайтов на ноутбук попасть не должны.
Настройки кластера – `/etc/postgresql/16/siteschool/conf.d/siteschool.conf`.

Redis общий (`redis-server`, localhost:6379), но школьный сайт занимает свои
базы: 1 для Celery и 2 для Channels. Они записаны в `.env`.

## Выкатка

Выкатка запускается с dev из Git Bash:

```bash
bash scripts/deploy.sh
```

lbm-srv получает полный деплой: `git pull`, `pip`, `migrate`, `collectstatic`,
`docker build site-sandbox-cpp` и перезапуск четырёх юнитов `siteschool-*`.
Ноутбук получает `git pull`, `pip`, `collectstatic` и `docker build`, но без
`migrate` (схема приходит репликой) и без перезапусков (сервисы выключены).

Если на ноутбуке стоит `.failover`, скрипт отказывается работать: основной
сервер в этот момент – ноутбук, и схема выкатки к нему не подходит.

Файлы, которых нет в git (собранные `.wasm` и архив спецкурса в
`static/spetskurs/`), по-прежнему выкладываются руками – на оба сервера. Порядок
описан в [выкладке спецкурса](spetskurs-deploy.md).

## Бэкап

Бэкап – `scripts/backup-prod-db.sh` на dev, запускается Планировщиком Windows.
Дамп снимается с основной базы на lbm-srv через Tailscale (`ssh lih@lbm-srv`) и
хранится в `C:\Users\Kirill\Backups\site-db`: десять последних копий.

## Проверка реплики

```bash
ssh lih@lbm-srv 'sudo -u postgres psql -p 5433 -c "select client_addr, state, write_lag, replay_lag from pg_stat_replication"'
ssh admin@192.168.1.199 -p 2222 'psql -h localhost -U siteschool -d siteschool -c "select now() - pg_last_xact_replay_timestamp() as lag"'
```

Вторая команда спросит пароль роли `siteschool` – он в `/home/admin/site/.env`.
Отставание растёт, когда на сайте нет записей, это нормально.

## Авария

lbm-srv лежит – сайт поднимается на ноутбуке:

```bash
ssh admin@192.168.1.199 -p 2222
sudo bash /home/admin/site/scripts/failover.sh
```

Скрипт отказывается работать, если PostgreSQL на lbm-srv отвечает: две основные
базы и два Beat хуже простоя. `--force` – на случай, если lbm-srv точно не
обслуживает учеников. Дальше он спрашивает `yes`, ставит `.failover`, делает
promote реплики (`pg_ctlcluster 16 main promote`), включает `site daphne celery
celerybeat` и переключает nginx на `site-local`.

После promote реплики больше нет – её придётся пересобирать (раздел «Сборка
реплики»). Если lbm-srv потом поднимется сам, его `siteschool-*` запустятся на
старой базе. Остановить их сразу:

```bash
sudo systemctl stop siteschool-web siteschool-daphne siteschool-celery siteschool-celerybeat
```

Учеников туда никто не пустит (nginx ноутбука смотрит на `site-local`), но Beat
там лишний.

## Возврат на lbm-srv

Простой на время возврата – страница обслуживания. Порядок:

1. lbm-srv: остановить сайт.

```bash
sudo systemctl stop siteschool-web siteschool-daphne siteschool-celery siteschool-celerybeat
```

2. Ноутбук: остановить сайт и вернуть шлюз. С остановленным lbm-srv шлюз
   показывает страницу обслуживания.

```bash
sudo systemctl disable --now site daphne celery celerybeat
sudo ln -sfn ../sites-available/site /etc/nginx/sites-enabled/site
sudo nginx -t && sudo systemctl reload nginx
```

3. Ноутбук: перенести базу и media на lbm-srv.

```bash
sudo -u postgres pg_dump -Fc siteschool | ssh lih@100.65.27.51 'sudo -u postgres psql -p 5433 -qc "DROP DATABASE IF EXISTS siteschool WITH (FORCE)" -c "CREATE DATABASE siteschool OWNER siteschool" && sudo -u postgres pg_restore -p 5433 --no-owner --no-acl --role=siteschool -d siteschool'
rsync -a /home/admin/site/media/ lih@100.65.27.51:/home/lih/siteSchool/media/
```

4. lbm-srv: запустить сайт.

```bash
sudo systemctl start siteschool-web siteschool-daphne siteschool-celery siteschool-celerybeat
```

Сайт открылся через шлюз. Проверить страницу, отправку кода Python и C++ с
ответом по WebSocket.

5. Пересобрать реплику (раздел ниже) и снять флаг.

```bash
rm /home/admin/site/.failover
```

## Сборка реплики

Сборка нужна при первой настройке и после аварии. Перед ней – свежий дамп базы
ноутбука, если в ней есть что-то ценное (`bash scripts/backup-prod-db.sh` снимает
с lbm-srv; базу ноутбука после аварии уже перенёс шаг 3).

На lbm-srv один раз уже сделано при первой сборке: роль `siteschool_replica` с
REPLICATION, строка в `/etc/postgresql/16/siteschool/pg_hba.conf`
`host replication siteschool_replica <Tailscale-IP ноутбука>/32 scram-sha-256`,
физический слот `siteschool_laptop`. Роль, строка `pg_hba` и слот переживают
пересборку. После аварии слот надо пересоздать: старый держит WAL для реплики,
которой больше нет.

```bash
sudo -u postgres psql -p 5433 -c "select pg_drop_replication_slot('siteschool_laptop')" -c "select pg_create_physical_replication_slot('siteschool_laptop')"
```

На ноутбуке (пароль `siteschool_replica` – в `/var/lib/postgresql/.pgpass`):

```bash
sudo systemctl stop postgresql@16-main
sudo -u postgres rm -rf /var/lib/postgresql/16/main
sudo -u postgres pg_basebackup -h 100.65.27.51 -p 5433 -U siteschool_replica -D /var/lib/postgresql/16/main -R -S siteschool_laptop -X stream -P
sudo systemctl start postgresql@16-main
```

`.env` ноутбука при этом смотрит на свою реплику: `DB_NAME=siteschool`,
`DB_USER=siteschool`, пароль тот же, что на lbm-srv, `DB_HOST=localhost`,
`DB_PORT=5432`. Роли приходят репликой.

## Учебная авария

Проверка `failover.sh` на живой системе – только по отдельному решению Кирилла.
После неё реплику пересобирать.
