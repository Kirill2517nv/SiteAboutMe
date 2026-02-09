# Образовательная платформа

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-6.0-green?logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.x-38B2AC?logo=tailwind-css&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-5.0-DC382D?logo=redis&logoColor=white)

Веб-платформа для управления уроками, тестами и учебными группами. Поддерживает асинхронную проверку Python-кода в реальном времени через WebSocket.

## Возможности

### Уроки
- Иерархия **Раздел > Урок > Блоки контента**
- Блочный конструктор: текст, изображения, комбинированные блоки
- Файловые вложения и видео-ссылки
- Превью-карточки с изображениями

### Тесты
- Три типа вопросов: **выбор ответа**, **свободный текст**, **Python-код**
- Назначение тестов группам и отдельным ученикам
- Ограничение попыток (глобальное и индивидуальное)
- Временные окна доступа
- Детальная статистика и результаты
- Архив завершённых тестов

### Система помощи
- Диалог ученик-учитель по каждому вопросу
- Комментарии к **конкретным строкам кода** (inline threads)
- Уведомления в реальном времени (WebSocket + polling)
- Авто-открытие диалога при клике по уведомлению

### Проверка кода в реальном времени
- Асинхронная проверка Python-кода через **Celery + Redis**
- Real-time обратная связь через **WebSocket** (Django Channels)
- Изолированная среда выполнения (Docker)
- Обновление UI без перезагрузки страницы

### Управление пользователями
- Авторизация (аккаунты создаёт преподаватель)
- Профили учеников с привязкой к учебным группам и флагом ЕГЭ
- Массовое назначение тестов через админ-панель

### Конструктор страниц
- Блочная система для главной страницы и страницы "Обо мне"
- Настройки шрифтов, цветов, выравнивания и фонов
- Обрезка и позиционирование изображений

## Технологии

| Технология | Роль |
|------------|------|
| **Django 6.0** | Веб-фреймворк |
| **PostgreSQL** | База данных |
| **Celery** | Асинхронные задачи (проверка кода) |
| **Redis** | Брокер сообщений для Celery и Channels |
| **Django Channels** | WebSocket-соединения |
| **Daphne** | ASGI-сервер (WebSocket) |
| **Gunicorn** | WSGI-сервер (HTTP) |
| **Nginx** | Reverse proxy, SSL |
| **Tailwind CSS** | Стилизация |
| **Alpine.js** | Интерактивность на клиенте |
| **Docker** | Песочница для выполнения кода |
| **WhiteNoise** | Раздача статических файлов |

## Быстрый старт

### Требования

- Python 3.12+
- PostgreSQL
- Redis
- Docker (для проверки кода)

### Установка

```bash
# Клонировать репозиторий
git clone https://github.com/Kirill2517nv/SiteAboutMe.git
cd SiteAboutMe

# Виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Зависимости
pip install -r requirements.txt

# Переменные окружения
cp .env.example .env
# Отредактировать .env: SECRET_KEY, DATABASE_URL, ...

# База данных
python manage.py migrate
python manage.py createsuperuser

# Запуск
python manage.py runserver
```

### Запуск с асинхронной проверкой кода

```bash
# Терминал 1: Redis
docker run -p 6379:6379 redis

# Терминал 2: Celery worker
celery -A config worker -l info --pool=solo -Q default,code_execution

# Терминал 3: Django
python manage.py runserver
```

## Структура проекта

```
├── config/             # Настройки Django (settings, urls, wsgi, asgi, celery)
├── accounts/           # Авторизация, профили, учебные группы
├── pages/              # Главная страница и "Обо мне" (блочный конструктор)
├── lessons/            # Разделы, уроки, блоки контента
├── quizzes/            # Тесты, вопросы, проверка кода, WebSocket
├── templates/          # HTML-шаблоны
├── static/             # CSS и JavaScript
├── requirements.txt    # Python-зависимости
└── manage.py
```

## Деплой

Продакшн-стек: **Gunicorn** (HTTP) + **Daphne** (WebSocket) + **Nginx** (reverse proxy) + **Celery** (async tasks).

```bash
# На сервере
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart site celery daphne
```

## Лицензия

Проект разработан для образовательных целей.
