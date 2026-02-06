# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Django 6.0.1 educational platform (Russian language) for managing lessons, quizzes, and student groups. Uses PostgreSQL, Tailwind CSS, and Alpine.js. Features async code execution for Python quizzes via Celery + Redis with real-time WebSocket feedback through Django Channels. Deployed with Gunicorn + Nginx + Daphne.

## Common Commands

```bash
pip install -r requirements.txt          # Install dependencies
python manage.py runserver               # Dev server at localhost:8000
python manage.py makemigrations          # Create migrations after model changes
python manage.py migrate                 # Apply migrations
python manage.py createsuperuser         # Create admin user
python manage.py collectstatic           # Collect static files for production
gunicorn config.wsgi:application         # Production server (HTTP)
daphne config.asgi:application           # ASGI server (WebSocket)
celery -A config worker -l info          # Celery worker for async tasks
```

### Local Development with Async Features
To test async code execution locally, run these in separate terminals:
1. Redis: `docker run -p 6379:6379 redis` (or install Redis locally)
2. Celery: `celery -A config worker -l info`
3. Django: `python manage.py runserver` (or `daphne -p 8000 config.asgi:application` for WebSocket)

## Architecture

**Django project config lives in `config/`** (settings, urls, wsgi/asgi).

Four apps, each with standard Django structure (models, views, urls, admin, forms):

- **accounts** — User auth, `Profile` (extends User with group assignment), `StudentGroup` for organizing students into classes
- **pages** — Home/about pages built from `ContentBlock` models with rich styling (fonts, colors, image crop/positioning)
- **lessons** — `Section` → `Lesson` → `LessonBlock` hierarchy. Supports file uploads, video URLs, and flexible content layouts. File downloads use Nginx X-Accel-Redirect in production.
- **quizzes** — `Quiz` with time-based access windows, `Question` (multiple choice, free text, Python code execution with `TestCase` validation), `QuizAssignment` (to groups or individuals), `UserResult`/`UserAnswer` for tracking. Attempt limiting with override support. `CodeSubmission` for async code execution results.

**Content block pattern**: Both `pages` and `lessons` use a reusable block model for flexible page composition with database-driven styling (fonts, colors, alignment, sizing).

**Async Code Execution System** (`quizzes` app):
- `consumers.py` — WebSocket consumer for real-time code submission updates
- `tasks.py` — Celery tasks for sandboxed Python code execution
- `routing.py` — WebSocket URL routing (`/ws/quiz/<quiz_id>/`)
- Frontend: `static/js/quiz-async.js` — WebSocket client, UI updates without page reload

## Key Configuration

- Database credentials and Django secret key in `.env`
- PostgreSQL via psycopg2-binary
- Redis: localhost:6379 (broker for Celery and Django Channels)
- Celery: configured in `config/celery.py`, tasks in `quizzes/tasks.py`
- Channels: configured in `config/asgi.py`, routing in `quizzes/routing.py`
- Timezone: Asia/Novosibirsk
- Media files: `media/` (content, lessons_files, question_files)
- Static assets: `static/css/` and `static/js/` (block-editor, content-editor-tailwind, quiz-async)
- Templates: `templates/` directory with subdirectories per app

## Infrastructure

### Development (Windows)
- This machine is used for development and testing
- Dev server: `python manage.py runserver` → http://localhost:8000

### Production Server
- **Host:** kirill-lab.ru
- **Local IP:** 192.168.1.199
- **OS:** Ubuntu 24.04
- **User:** admin
- **Connect:** `ssh admin@192.168.1.199 -p 2222`
- **Project path:** `/home/admin/site`

### Services
- **Nginx:** `/etc/nginx/sites-available/site` (proxies HTTP to Gunicorn, WebSocket to Daphne)
- **Gunicorn:** `site.service` (socket: `/run/gunicorn/site.sock`) — HTTP requests
- **Daphne:** `daphne.service` (socket: `/run/daphne/site.sock`) — WebSocket requests
- **Celery:** `celery.service` — async task worker for code execution
- **Redis:** `redis-server.service` — message broker for Celery and Channels
- **PostgreSQL:** local database
- **SSL:** Certbot (Let's Encrypt)

### Deployment (on server)
```bash
ssh admin@192.168.1.199 -p 2222
cd /home/admin/site
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart site celery daphne
```

### Useful Commands (on server)
```bash
# Status of all services
sudo systemctl status redis-server celery daphne site nginx

# Restart services
sudo systemctl restart site celery daphne  # App services
sudo systemctl restart nginx               # Web server

# Logs
sudo journalctl -u site -f                 # Gunicorn (HTTP)
sudo journalctl -u daphne -f               # Daphne (WebSocket)
sudo journalctl -u celery -f               # Celery (async tasks)
sudo tail -f /var/log/nginx/error.log      # Nginx errors

# Redis
redis-cli ping                             # Should return PONG
```

## Skills (Slash-команды)

Проект включает систему агентов и slash-команд в `.claude/skills/`. Полная документация: `.claude/skills/README.md`

### Доступные команды

| Категория | Команда | Описание |
|-----------|---------|----------|
| **Дизайн** | `/design-audit [URL]` | UI/UX аудит страницы через Playwright |
| | `/design-component [name]` | Создать Tailwind компонент |
| | `/design-guide` | Сгенерировать DESIGN.md |
| **Ревью** | `/review-code [target]` | Код-ревью (файл, коммит, PR) |
| | `/review-security` | Полный аудит безопасности |
| | `/create-issue [type] [title]` | Создать GitHub issue |
| | `/create-release [version]` | Создать релиз с changelog |
| **Контент** | `/create-quiz [topic]` | Создать Quiz в формате fixtures |
| | `/import-ege [source]` | Импорт задачи ЕГЭ |
| | `/generate-ideas [area]` | Генерация идей развития |
| **DevOps** | `/diagnose` | Полная диагностика системы |
| | `/check-logs [service] [period]` | Логи сервиса (1h/6h/1d/7d) |
| | `/check-services` | Статус всех сервисов |

### Агенты

- 🎨 **designer** — UI/UX, Tailwind, Playwright скриншоты
- 🔍 **reviewer** — безопасность, GitHub, код-ревью
- 📚 **content** — Quiz, ЕГЭ задачи, fixtures
- 🔧 **devops** — диагностика (**READ-ONLY!**)
