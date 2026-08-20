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
npm run tw:build                         # ОБЯЗАТЕЛЬНО после новых Tailwind-классов в шаблонах
npm run tw:watch                         # Пересборка CSS на лету во время вёрстки
python manage.py load_quiz <file.json>   # Import quiz from JSON fixture
gunicorn config.wsgi:application         # Production server (HTTP)
daphne config.asgi:application           # ASGI server (WebSocket)
celery -A config worker -l info          # Celery worker for async tasks
celery -A config beat -l info            # Celery Beat periodic scheduler
```

### Local Development with Async Features
To test async code execution locally, run these in separate terminals:
1. Redis: `docker run -p 6379:6379 redis` (or install Redis locally)
2. Celery: `celery -A config worker -l info`
3. Django: `python manage.py runserver` (or `daphne -p 8000 config.asgi:application` for WebSocket)

## Architecture

**Django project config lives in `config/`** (settings, urls, wsgi/asgi).

Four apps, each with standard Django structure (models, views, urls, admin, forms):

- **accounts** — User auth, `Profile` (extends User with group assignment, `is_ege` flag), `StudentGroup` for organizing students into classes. `ProfileView` shows two stat blocks: **Учебник** (per-`Section` grades, lessons read, practicum tasks, reading time, «что подтянуть» — via `textbook.services.profile_textbook_stats`) and **ЕГЭ** (trainer progress by EGE task number 1–27, variants, theory articles — via `accounts.views._ege_stats`). Superusers open any student's profile at `accounts:student_profile` (`profile/<user_id>/`); students get 403 on foreign profiles. `templatetags/profile_tags.py` provides the `duration_display` filter for timedelta formatting.
- **pages** — Home/about pages built from `ContentBlock` models with rich styling (fonts, colors, image crop/positioning)
- **lessons** — `Section` → `Lesson` → `LessonAttachment` / `LessonBlock` hierarchy. `LessonAttachment` stores multiple downloadable files per lesson. `Lesson` supports Slidev presentations (`presentation_url`, `presentation_title`, `presentation_pdf`) and video URLs. All file uploads use a unified path `media/lessons/{safe_title}/`. File downloads use Nginx X-Accel-Redirect in production. Dev server serves media with `index.html` fallback for Slidev SPA.
- **quizzes** — `Quiz` with time-based access windows, `Question` (multiple choice, free text, Python code execution with `TestCase` validation, `title` field), `QuizAssignment` (to groups or individuals), `UserResult`/`UserAnswer` for tracking. Attempt limiting with override support. `CodeSubmission` for async code execution results. `HelpRequest`/`HelpComment` for teacher-student dialogue with inline line comments.

**Content block pattern**: Both `pages` and `lessons` use a reusable block model for flexible page composition with database-driven styling (fonts, colors, alignment, sizing).

**Async Code Execution System** (`quizzes` app):
- `consumers.py` — WebSocket consumers: `QuizConsumer` for code submissions, `NotificationConsumer` for help notifications
- `tasks.py` — Celery tasks for sandboxed Python code execution
- `routing.py` — WebSocket URL routing (`/ws/quiz/<quiz_id>/`, `/ws/notifications/`)
- Frontend: `static/js/quiz-async.js` — WebSocket client with connection status tracking, UI updates without page reload

**Help Request System** (`quizzes` app):
- `views.py` — help_request_view (GET with `mark_read` param, POST), help_request_list, help_request_review
- Frontend: `static/js/help-requests.js` — HelpRequestManager with inline line threads, gutter click handling, line markers
- Frontend: `static/js/notifications.js` — NotificationManager with WebSocket + polling fallback, dropdown UI

## Key Configuration

- Database credentials and Django secret key in `.env`
- PostgreSQL via psycopg2-binary
- Redis: localhost:6379 (broker for Celery and Django Channels)
- Celery: configured in `config/celery.py`, tasks in `quizzes/tasks.py`
- Channels: configured in `config/asgi.py`, routing in `quizzes/routing.py`
- Timezone: Asia/Novosibirsk
- **Tailwind CSS is precompiled**, not a CDN build: `static/css/tailwind.css` is generated from `static/css/tailwind.input.css` by `npm run tw:build` (config: `tailwind.config.js`, scans `templates/**/*.html` and `static/js/**/*.js`). A class that no template used before simply does not exist in the CSS until you rebuild — the browser silently ignores it and the layout looks unchanged. Always run `npm run tw:build` after adding new utility classes.
- Media files: `media/` (`lessons/{safe_title}/` for lesson files/presentations, `question_files/` for quiz files, `content/` for pages)
- Static assets: `static/js/` (quiz-async, help-requests, notifications, ege-timer)
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
- **Celery Beat:** `celerybeat.service` — periodic task scheduler (stale task cleanup, etc.)
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
sudo systemctl restart site celery celerybeat daphne
```

### Useful Commands (on server)
```bash
# Status of all services
sudo systemctl status redis-server celery celerybeat daphne site nginx

# Restart services
sudo systemctl restart site celery celerybeat daphne  # App services
sudo systemctl restart nginx               # Web server

# Logs
sudo journalctl -u site -f                 # Gunicorn (HTTP)
sudo journalctl -u daphne -f               # Daphne (WebSocket)
sudo journalctl -u celery -f               # Celery (async tasks)
sudo journalctl -u celerybeat -f           # Celery Beat (periodic scheduler)
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
| **Контент** | `/create-quiz [topic]` | Создать Quiz через AI генерацию |
| | `/generate-ideas [area]` | Генерация идей развития |
| **DevOps** | `/diagnose` | Полная диагностика системы |
| | `/check-logs [service] [period]` | Логи сервиса (1h/6h/1d/7d) |
| | `/check-services` | Статус всех сервисов |

### Агенты

- 🎨 **designer** — UI/UX, Tailwind, Playwright скриншоты
- 🔍 **reviewer** — безопасность, GitHub, код-ревью
- 📚 **content** — Quiz генерация, идеи развития
- 🔧 **devops** — диагностика (**READ-ONLY!**)

### Quiz Import (`load_quiz`)

Management command for importing quizzes from JSON files. Uses a custom format (not Django fixtures) — no `pk` required, Django assigns IDs automatically. All objects are created in a single transaction.

```bash
python manage.py load_quiz fixtures/my_quiz.json
```

- JSON format template: `fixtures/quiz_template.json`
- Supports all 3 question types: `choice` (with choices), `text` (with correct_text_answer), `code` (with test_cases)
- Code questions can optionally include `data_file` path for attached files
- Command: `quizzes/management/commands/load_quiz.py`

### Примечание о парсинге

**Парсинг учебных сайтов (kompege.ru, reshuege.ru) вынесен в отдельное GUI приложение.**
См. `PARSING_APP.md` для деталей о новом workflow создания тестов через парсинг.
