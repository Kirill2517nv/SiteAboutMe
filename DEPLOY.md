# Инструкция по развёртыванию на Ubuntu/Debian

## 1. Обновление системы и установка базовых пакетов

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx postgresql postgresql-contrib
```

## 2. Настройка PostgreSQL

```bash
sudo -u postgres psql
```

В psql:

```sql
CREATE DATABASE mydb;
CREATE USER myuser WITH PASSWORD 'надёжный_пароль';
ALTER ROLE myuser SET client_encoding TO 'utf8';
ALTER ROLE myuser SET default_transaction_isolation TO 'read committed';
ALTER ROLE myuser SET timezone TO 'Asia/Novosibirsk';
GRANT ALL PRIVILEGES ON DATABASE mydb TO myuser;
ALTER DATABASE mydb OWNER TO myuser;
\q
```

## 3. Клонирование проекта

```bash
cd /home
sudo mkdir -p /home/site
cd /home/site
git clone https://github.com/Kirill2517nv/SiteAboutMe.git app
cd app
```

## 4. Виртуальное окружение и зависимости

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 5. Создание `.env` файла

```bash
nano .env
```

Содержимое:

```
SECRET_KEY=сгенерируй_длинный_случайный_ключ
DEBUG=False
DB_NAME=mydb
DB_USER=myuser
DB_PASSWORD=надёжный_пароль
DB_HOST=localhost
DB_PORT=5432
USE_X_ACCEL_REDIRECT=True
```

Для генерации секретного ключа:

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 6. Миграции и статика

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

## 7. Настройка Gunicorn как systemd-сервиса

```bash
sudo nano /etc/systemd/system/site.service
```

Содержимое:

```ini
[Unit]
Description=Django Site Gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/home/site/app
ExecStart=/home/site/app/venv/bin/gunicorn config.wsgi:application --bind unix:/home/site/app/gunicorn.sock --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown -R www-data:www-data /home/site/app
sudo systemctl daemon-reload
sudo systemctl enable site
sudo systemctl start site
```

## 8. Настройка Nginx

Замени `твой-домен.ru` на свой домен:

```bash
sudo nano /etc/nginx/sites-available/site
```

```nginx
server {
    listen 80;
    server_name твой-домен.ru www.твой-домен.ru;

    client_max_body_size 50M;

    location /static/ {
        alias /home/site/app/staticfiles/;
    }

    location /media/ {
        alias /home/site/app/media/;
    }

    # Для X-Accel-Redirect (скачивание файлов через Nginx)
    location /protected_media/ {
        internal;
        alias /home/site/app/media/;
    }

    location / {
        proxy_pass http://unix:/home/site/app/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/site /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## 9. SSL с Let's Encrypt (бесплатный HTTPS)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d твой-домен.ru -d www.твой-домен.ru
```

Certbot автоматически настроит Nginx для HTTPS и добавит автопродление.

## 10. Обновление ALLOWED_HOSTS

В `config/settings.py` замени `ALLOWED_HOSTS = ['*']` на свой домен:

```python
ALLOWED_HOSTS = ['твой-домен.ru', 'www.твой-домен.ru']
```

Или лучше вынеси в `.env` и парси через `os.getenv`.

## Полезные команды для отладки

```bash
sudo journalctl -u site -f            # логи Gunicorn
sudo tail -f /var/log/nginx/error.log  # логи Nginx
sudo systemctl restart site            # перезапуск приложения
sudo systemctl restart nginx           # перезапуск Nginx
```
