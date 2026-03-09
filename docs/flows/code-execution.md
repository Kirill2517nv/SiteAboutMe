# Выполнение кода

Async pipeline: клиент → Django → Celery → Docker → WebSocket → клиент.

---

## Общая архитектура

```mermaid
flowchart LR
    subgraph Frontend
        JS[quiz-async.js\nQuizCodeChecker]
    end

    subgraph Django
        VIEW[submit_code_view]
        CONSUMER[QuizConsumer\nWebSocket]
    end

    subgraph Celery
        TASK[check_code_task]
    end

    subgraph Docker
        CONTAINER[python:3.11-slim\nsandbox]
    end

    JS -->|"POST /submit/"| VIEW
    VIEW -->|"CodeSubmission\nstatus=pending"| DB[(Database)]
    VIEW -->|"task.delay()"| TASK
    TASK -->|"run_code_in_docker()"| CONTAINER
    CONTAINER -->|"stdout/stderr\nmetrics"| TASK
    TASK -->|"Обновить\nCodeSubmission"| DB
    TASK -->|"channel_layer\ngroup_send()"| CONSUMER
    CONSUMER -->|"WS message"| JS
```

---

## Отправка кода (Frontend → Backend)

```mermaid
sequenceDiagram
    participant U as Ученик
    participant JS as QuizCodeChecker
    participant API as submit_code_view
    participant DB as Database
    participant C as Celery

    U->>JS: Нажать "Проверить"
    JS->>JS: Проверить нет ли pending
    JS->>API: POST /quizzes/5/question/3/submit/\n{code: "..."}

    API->>DB: Проверить QuizAssignment
    API->>DB: Проверить pending submissions
    alt Уже есть pending
        API-->>JS: 409 Conflict
    end
    API->>DB: Создать CodeSubmission(status=pending)
    API->>C: check_code_task.delay(id)
    API-->>JS: 200 {submission_id, status: "pending"}
    JS->>JS: Добавить в pendingSubmissions
    JS->>U: UI: "Проверяется..."
```

---

## Docker Sandbox

### Ресурсные лимиты

| Параметр | Значение | Описание |
|----------|----------|----------|
| `CONTAINER_TIMEOUT` | 150 сек | Максимальное время жизни контейнера |
| `CONTAINER_MEM_LIMIT` | 128 MB | Лимит оперативной памяти |
| `CONTAINER_CPU_QUOTA` | 100000 | 100% одного ядра CPU |
| `OUTPUT_MAX_BYTES` | 64 KB | Максимальный размер stdout |
| Network | Отключена | Контейнер не имеет сети |

### Процесс выполнения

```mermaid
flowchart TD
    START[run_code_in_docker] --> PING{docker.ping}
    PING -->|Ошибка| ERR_DOCKER[Ошибка: Docker не запущен]
    PING -->|OK| CREATE[Создать контейнер\npython:3.11-slim]
    CREATE --> TAR[Подготовить tar-архив]

    TAR --> FILES["solution.py — код ученика\nrunner.py — обёртка с метриками\n+ extra_files (если есть)"]
    FILES --> UPLOAD[put_archive /app/]
    UPLOAD --> EXEC["exec_run:\nprintf 'input' | python runner.py"]

    EXEC --> EXIT{exit_code?}
    EXIT -->|0| PARSE_OK[Парсинг stdout + метрики\nиз stderr]
    EXIT -->|137| TIMEOUT[Превышен лимит\nвремени или памяти]
    EXIT -->|другой| ERROR[Ошибка выполнения\n+ stderr]

    PARSE_OK --> TRUNC{stdout > 64KB?}
    TRUNC -->|Да| CUT[Обрезать + пометка]
    TRUNC -->|Нет| RETURN[Вернуть результат]
    CUT --> RETURN

    RETURN --> CLEANUP[container.remove\nforce=True]
    TIMEOUT --> CLEANUP
    ERROR --> CLEANUP
```

### Runner Script (runner.py)

Обёртка, которая выполняет код ученика и собирает метрики:

```
1. Прочитать solution.py
2. Перехватить stdin → StringIO
3. Перехватить stdout → StringIO
4. exec(code) с подменённым stdin/stdout
5. Вывести stdout ученика
6. stderr: __CPU_TIME_MS__:45.123
7. stderr: __MEMORY_KB__:8192
```

Метрики:
- **CPU time** — `time.process_time()` (только CPU, не wall-clock)
- **Memory** — `resource.getrusage(RUSAGE_SELF).ru_maxrss` (пиковое RSS, Linux)

---

## Celery Task Pipeline

```mermaid
sequenceDiagram
    participant C as check_code_task
    participant DB as Database
    participant D as Docker
    participant WS as channel_layer

    C->>DB: Получить CodeSubmission + Question
    C->>DB: status = 'running'
    C->>WS: send('running')

    loop Каждый TestCase
        C->>D: run_code_in_docker(code, input)
        D-->>C: output, error, cpu_time, memory
        C->>C: normalize_output(output)\nvs test_case.output_data
        alt Ошибка или несовпадение
            C->>C: all_tests_passed = False
            Note over C: break из цикла
        end
        C->>C: Накопить total_cpu,\npeak_memory
    end

    C->>DB: Обновить CodeSubmission\nis_correct, status, metrics
    C->>C: update_user_answer_from_submission
    C->>C: update_exam_progress_from_submission
    C->>DB: Обновить UserAnswer +\nUserResult.score
    C->>DB: Обновить ExamTaskProgress\nbest metrics
    C->>WS: send('completed')
```

### Обновление результатов

После проверки кода Celery task обновляет связанные записи:

**update_user_answer_from_submission:**
1. Найти `UserAnswer` связанный с `CodeSubmission`
2. Обновить `is_correct`, `error_log`, `code_answer`
3. Пересчитать `UserResult.score`:
   - Standard: count distinct correct questions
   - Exam: sum points for correct questions

**update_exam_progress_from_submission:**
1. Найти/создать `ExamTaskProgress`
2. Обновить `is_solved`, `first_solved_at`
3. Обновить лучшие метрики (если лучше предыдущих):
   - `best_cpu_time_ms` + `best_cpu_code`
   - `best_memory_kb` + `best_memory_code`

---

## WebSocket обновления

### QuizConsumer

| Событие | Payload | Когда |
|---------|---------|-------|
| `submission_update` | `{submission_id, question_id, status, is_correct, error_log, cpu_time_ms, memory_kb}` | При изменении статуса |
| `active_submissions` | `[{id, question_id, status}]` | При connect + по запросу |

**Группа:** `user_{user_id}_quiz_{quiz_id}` — изоляция на уровне пользователь+тест.

### Reconnection & Fallback

```mermaid
flowchart TD
    WS[WebSocket подключение] --> OPEN{Успешно?}
    OPEN -->|Да| LISTEN[Слушать события]
    OPEN -->|Нет| RETRY{Попытка < 5?}
    RETRY -->|Да| BACKOFF["Ждать 1s, 2s, 4s, 8s, 16s"]
    BACKOFF --> WS
    RETRY -->|Нет| POLLING[Fallback: polling\nкаждые 2 секунды]
    POLLING --> POLL_EP["GET /submission/id/status/"]

    LISTEN --> CLOSE{WS закрыт?}
    CLOSE -->|Да| RETRY
```

---

## Очистка зависших задач

`cleanup_stale_submissions()` — периодическая задача Celery Beat (каждые 3 минуты):

1. Найти `CodeSubmission` со статусом `pending`/`running` старше 10 минут
2. Установить `status='error'`, `error_log='Превышено время ожидания'`
3. Обновить связанные `UserAnswer`
4. Отправить WS-уведомление

!!! warning "Почему задачи зависают"
    - Docker контейнер завершился по OOM, но Celery не получил результат
    - Celery worker перезапустился во время выполнения
    - Сетевая ошибка между Celery и Redis
