# Образовательная платформа

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-6.0-green?logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.x-38B2AC?logo=tailwind-css&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-5.0-DC382D?logo=redis&logoColor=white)

Веб-платформа для школы и кружка: учебник с теорией и практикумом, тренажёр ЕГЭ по информатике, годовой курс численного моделирования на C++, тесты, учебные группы и «Своя игра». Проверка Python-кода идёт асинхронно, результат приходит в браузер по WebSocket – без перезагрузки страницы.

## Возможности

### Учебник
- Иерархия **Раздел → Статья → Блоки контента**
- Один тип статьи на три трека: уроки, теория ЕГЭ, спецкурс
- Блоки контента: текст, код, изображение, видео, формула (LaTeX) и интерактивный виджет
- Тесты-самопроверки по ходу чтения и задания практикума, отметка о прочтении и учёт времени чтения
- Режим показа с проектора: статья разворачивается на весь экран и листается по блокам
- Отчёт учителя по разделу: кто прочитал, кто решил практикум, разбор ответов с ошибками

### Тренажёр ЕГЭ
- Карта всех 27 заданий с теорией и личной статистикой по каждому
- «Тренировка» – проверка сразу после ответа; «Экзамен» – проверка в конце, ответы можно менять до истечения времени
- Готовые варианты в формате экзамена и банк задач по номерам
- Прогноз балла, слабые места, разбор ошибок и архив решённых задач
- Работа над ошибками и повторное решение задач по коду
- Таблица класса для учителя и просмотр статистики отдельного ученика

### Тесты
- Три типа вопросов: **выбор ответа**, **свободный текст**, **Python-код**
- Назначение тестов группам и отдельным ученикам
- Ограничение попыток (общее и индивидуальное) и временные окна доступа
- Подсказки к задачам по правилам раздела
- Статистика по тесту и разбор каждой попытки

### Спецкурс
- Годовой курс численного моделирования на C++
- Каждая задача связывает физику, исходник `main.cpp` и WASM-симуляцию, запускаемую прямо в браузере
- Разборы задач и раздел «Основы C++» живут на моделях учебника и выпускаются по мере вычитки
- Архив исходников библиотеки курса – в статье «Программа, сборка и запуск», рядом со ссылкой на `git clone`

### «Своя игра»
- Ученики предлагают темы и вопросы, учитель их модерирует
- Сборка игровых паков из одобренных вопросов
- Игровые сессии: поле и список игроков хранятся в самой сессии

### Проверка кода в реальном времени
- Асинхронный запуск решения в изолированном **Docker**-контейнере (без сети, от непривилегированного пользователя, с лимитами памяти, CPU и числа процессов)
- Обратная связь через **Celery + Redis** и **WebSocket** (Django Channels)
- Обновление интерфейса без перезагрузки страницы

### Пользователи
- Учётные записи создаёт преподаватель
- Профили учеников с привязкой к учебной группе, флагом ЕГЭ и статистикой по учебнику
- Раздельная статистика: учебник – в профиле, номера ЕГЭ – на вкладке «Мой прогресс» тренажёра
- Страница выпускников с фотографиями и словом учителя о классе

### Главная и «Обо мне»
- Главная страница собирается из блоков контента, «Обо мне» – из профиля автора, фотографий, видео и событий
- Страница изменений парсится из `CHANGELOG.md`

## Технологии

| Технология | Роль |
|------------|------|
| **Django 6.0** | Веб-фреймворк |
| **PostgreSQL** | База данных |
| **Celery** | Асинхронные задачи (проверка кода, пересчёт сложности задач) |
| **Redis** | Брокер сообщений для Celery и Channels |
| **Django Channels** | WebSocket-соединения |
| **Daphne** | ASGI-сервер (WebSocket) |
| **Gunicorn** | WSGI-сервер (HTTP) |
| **Nginx** | Reverse proxy, SSL, отдача файлов через X-Accel-Redirect |
| **Tailwind CSS** | Стилизация (собирается заранее через npm) |
| **Alpine.js** | Интерактивность на клиенте |
| **CodeMirror 5** | Редактор кода в задачах |
| **MathJax** | Рендеринг формул LaTeX |
| **Slidev** | Презентации к урокам |
| **Docker** | Песочница для выполнения кода |
| **WhiteNoise** | Раздача статических файлов |

## Быстрый старт

### Требования

- Python 3.12+
- PostgreSQL
- Redis
- Docker (для проверки кода)
- Node.js (для сборки Tailwind CSS)

### Установка

```bash
# Клонировать репозиторий
git clone https://github.com/Kirill2517nv/SiteAboutMe.git
cd SiteAboutMe

# Виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Зависимости Python
pip install -r requirements.txt

# Зависимости и сборка фронтенда
npm install
npm run tw:build

# Переменные окружения: создать файл .env в корне
# SECRET_KEY, DEBUG, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT,
# CELERY_BROKER_URL, CELERY_RESULT_BACKEND, REDIS_HOST, REDIS_PORT

# База данных
python manage.py migrate
python manage.py createsuperuser

# Запуск
python manage.py runserver
```

`static/css/tailwind.css` собирается заранее, а не через CDN: класс, которого не было ни в одном шаблоне, попросту отсутствует в CSS, пока не выполнен `npm run tw:build`. При вёрстке удобнее держать запущенным `npm run tw:watch`.

### Запуск с асинхронной проверкой кода

```bash
# Терминал 1: Redis
docker run -p 6379:6379 redis

# Терминал 2: Celery worker
celery -A config worker -l info --pool=solo -Q default,code_execution

# Терминал 3: планировщик периодических задач (необязательно)
celery -A config beat -l info

# Терминал 4: Django
python manage.py runserver
```

Очередь `code_execution` объявлена в `config/celery.py` – задачи проверки кода уходят в неё отдельно от остальных, поэтому worker должен слушать обе очереди.

## Импорт тестов из JSON

Тесты можно загружать из JSON-файлов через management command. Формат поддерживает все три типа вопросов.

```bash
python manage.py load_quiz fixtures/my_quiz.json
```

Шаблон формата: `fixtures/quiz_template.json`

Пример структуры:
```json
{
  "quiz": {
    "title": "Название теста",
    "description": "Описание",
    "max_attempts": 3
  },
  "questions": [
    {
      "title": "Выбор ответа",
      "text": "Сколько будет 2+2?",
      "question_type": "choice",
      "choices": [
        {"text": "3", "is_correct": false},
        {"text": "4", "is_correct": true}
      ]
    },
    {
      "title": "Текстовый ответ",
      "text": "Столица Франции?",
      "question_type": "text",
      "correct_text_answer": "Париж"
    },
    {
      "title": "Задача на код",
      "text": "Выведите сумму двух чисел",
      "question_type": "code",
      "test_cases": [
        {"input_data": "2\n3", "output_data": "5"}
      ]
    }
  ]
}
```

Варианты ЕГЭ и банки задач по номерам импортируются отдельной командой; дедупликация идёт по `external_id`, поэтому повторный импорт обновляет задачи, а не создаёт дубли:

```bash
python manage.py load_ege fixtures/bank-1.json
```

Формат описан в `docs/ege-bank-format.md`.

## Команды управления

### Учебник и теория ЕГЭ

```bash
python manage.py seed_textbook_structure      # скелет учебника: разделы и заголовки статей
python manage.py seed_textbook_block<N>       # контент блока N (команды с 1 по 13)
python manage.py seed_ege_tasks               # 27 заданий ЕГЭ + заготовки статей
python manage.py seed_ege_theory_<N>          # наполнить разбор одного задания
python manage.py attach_article_images        # привязать картинки к статьям
python manage.py check_articles --track ege   # проверка статей в БД: формулы, ссылки, порядок блоков
python manage.py fix_dashes --dry-run         # найти длинные тире в БД (без флага – заменить)
```

### Спецкурс

```bash
python manage.py seed_spetskurs_basics        # «Основы C++», публикуется сразу
python manage.py seed_spetskurs_<задача>      # черновик разбора задачи
python manage.py publish_spetskurs <задача>   # выпустить разбор (или отдельные статьи по слагам)
```

### Банк задач ЕГЭ

```bash
python manage.py recalc_ege_difficulty --dry-run             # сложность по реальной доле верных первых попыток
python manage.py retag_ege --from 2 --to 5 --dry-run         # изменился кодификатор: перенести задачи номера
python manage.py mark_exam_pool --dry-run                    # заполнить резерв для экзамена
python manage.py ege_pools --dump fixtures/ege-pools.json    # снимок пулов для переноса на прод
```

## Структура проекта

```
├── config/             # Настройки Django (settings, urls, wsgi, asgi, celery)
├── accounts/           # Авторизация, профили, учебные группы, выпускники
├── pages/              # Главная страница и «Обо мне»
├── lessons/            # Разделы, уроки, вложения, Slidev-презентации
├── textbook/           # Учебник: статьи, теория ЕГЭ, практикум, спецкурс
├── quizzes/            # Тесты, вопросы, проверка кода, тренажёр ЕГЭ, WebSocket
├── spetskurs/          # Курс численного моделирования на C++ (задачи и WASM)
├── games/              # «Своя игра»: вопросы учеников, модерация, игровые паки
├── fixtures/           # JSON-шаблоны и данные для импорта
├── templates/          # HTML-шаблоны
├── static/             # CSS и JavaScript
├── docs/               # Документация для разработчика (MkDocs)
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
npm run tw:build
sudo systemctl restart site celery celerybeat daphne
```

## Лицензия

Проект разработан для образовательных целей.
