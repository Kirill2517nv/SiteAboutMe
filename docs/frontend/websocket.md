# WebSocket

Два WebSocket consumer'а обеспечивают real-time коммуникацию: результаты проверки кода и уведомления о помощи.

---

## Архитектура

```mermaid
flowchart TB
    subgraph Browser["Браузер"]
        QCC[QuizCodeChecker\nquiz-async.js]
        NM[NotificationManager\nnotifications.js]
    end

    subgraph Django["Django Channels"]
        QC[QuizConsumer]
        NC[NotificationConsumer]
    end

    subgraph Backend["Backend"]
        CELERY[Celery Task\ncheck_code_task]
        VIEW[help_request_view]
    end

    QCC <-->|"ws/quiz/ID/"| QC
    NM <-->|"ws/notifications/"| NC

    CELERY -->|"group_send\nsubmission_update"| QC
    VIEW -->|"group_send\nhelp_comment_update"| QC
    VIEW -->|"group_send\nhelp_notification"| NC
```

---

## QuizConsumer (`ws/quiz/<quiz_id>/`)

Обновления статуса проверки кода в реальном времени.

### Группы

```
user_{user_id}_quiz_{quiz_id}
```

Каждый пользователь в каждом тесте — отдельная группа. Изоляция гарантирует, что результаты видны только автору.

### Протокол

```mermaid
sequenceDiagram
    participant C as QuizCodeChecker
    participant QC as QuizConsumer
    participant CL as Celery

    C->>QC: WebSocket connect
    QC->>QC: Проверить auth (reject anonymous)
    QC->>QC: Join group user_X_quiz_Y
    QC-->>C: accept()
    QC-->>C: active_submissions [{id, question_id, status}]

    Note over C,QC: Клиент отправляет код через HTTP POST

    CL->>QC: group_send: submission_update
    QC-->>C: {type, submission_id, question_id,\nstatus, is_correct, error_log,\ncpu_time_ms, memory_kb}

    C->>QC: {action: "get_status"}
    QC-->>C: active_submissions [...]

    C->>QC: WebSocket close
    QC->>QC: Discard from group
```

### Типы сообщений

**Server → Client:**

| Тип | Поля | Когда |
|-----|------|-------|
| `active_submissions` | `submissions: [{id, question_id, status}]` | При connect и по запросу |
| `submission_update` | `submission_id, question_id, status, is_correct, error_log, event_type, cpu_time_ms, memory_kb` | При изменении статуса (running → success/failed/error) |
| `help_comment_update` | `question_id, comment, status, resolved` | При ответе учителя на inline-тред |

**Client → Server:**

| Действие | Payload | Эффект |
|----------|---------|--------|
| `get_status` | `{}` | Повторная отправка active_submissions |

---

## NotificationConsumer (`ws/notifications/`)

Badge-уведомления о запросах помощи.

### Группы

```mermaid
flowchart TD
    CONNECT[WebSocket connect] --> AUTH{Authenticated?}
    AUTH -->|Нет| REJECT[reject]
    AUTH -->|Да| PERSONAL["Join: notifications_{user_id}"]
    PERSONAL --> SUPER{is_superuser?}
    SUPER -->|Да| TEACHERS["Join: notifications_teachers"]
    SUPER -->|Нет| SEND_COUNT
    TEACHERS --> SEND_COUNT[Отправить unread_count]
```

- **Personal group** (`notifications_{user_id}`) — уведомления для конкретного ученика
- **Teachers group** (`notifications_teachers`) — уведомления для всех учителей (superusers)

### Протокол

```mermaid
sequenceDiagram
    participant NM as NotificationManager
    participant NC as NotificationConsumer
    participant VIEW as help_request_view

    NM->>NC: WebSocket connect
    NC-->>NM: {type: "unread_count_update", count: 3}

    Note over VIEW: Ученик создаёт комментарий

    VIEW->>NC: group_send(notifications_teachers)\nhelp_notification
    NC-->>NM: {type: "help_notification",\nhelp_request_id, quiz_id, question_id}
    NM->>NM: updateBadge(count + 1)

    Note over VIEW: Учитель отвечает

    VIEW->>NC: group_send(notifications_{student_id})\nhelp_notification
    NC-->>NM: {type: "help_notification", ...}
    NM->>NM: updateBadge(count)
```

### Unread Count Query

```python
# @database_sync_to_async
def get_unread_count():
    if user.is_superuser:
        # Все открытые/answered запросы с непрочитанными для учителя
        HelpRequest.filter(has_unread_for_teacher=True)
                   .exclude(status='resolved').count()
    else:
        # Запросы ученика с непрочитанными ответами
        HelpRequest.filter(student=user, has_unread_for_student=True).count()
```

---

## Frontend: QuizCodeChecker

Класс в `quiz-async.js` — клиентская часть WebSocket-протокола.

### Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Connecting: constructor
    Connecting --> Connected: onopen
    Connecting --> Reconnecting: onerror/timeout

    Connected --> Disconnected: onclose
    Connected --> Connected: onmessage

    Disconnected --> Reconnecting: auto
    Reconnecting --> Connected: onopen
    Reconnecting --> Polling: 5 failed attempts

    Polling --> Connected: WS восстановлен
    Polling --> Polling: каждые 2 сек
```

### Reconnection Strategy

| Попытка | Задержка | Действие |
|---------|----------|----------|
| 1 | 1 сек | Переподключение |
| 2 | 2 сек | Переподключение |
| 3 | 4 сек | Переподключение |
| 4 | 8 сек | Переподключение |
| 5 | 16 сек | Переподключение |
| 6+ | — | Переход на polling (каждые 2 сек) |

При reconnect: если есть `pendingSubmissions` — немедленно выполняет `_pollOnce()` для получения пропущенных обновлений.

### Polling Fallback

```
GET /quizzes/submission/{id}/status/
→ {status, is_correct, error_log, cpu_time_ms, memory_kb}
```

Polling активируется только при потере WebSocket и работает для каждой pending submission.

---

## Frontend: NotificationManager

Класс в `notifications.js` — badge-счётчик + dropdown.

### Badge UI

```
Есть непрочитанные:  🔔 3
Нет непрочитанных:   🔔 (скрыт)
Больше 99:           🔔 99+
```

Элемент: `#help-badge-global`

### Dropdown

При клике на badge загружает список уведомлений:

```
GET /quizzes/help-requests/my-notifications/
→ {notifications: [{quiz_id, quiz_title, question_id, question_title,
    status, preview, teacher_name, updated_at}]}
```

Каждое уведомление — ссылка:
```
/quizzes/{quiz_id}/?open_help={question_id}#question-{question_id}
```

### Reconnection

| Попытка | Задержка |
|---------|----------|
| 1 | 2 сек |
| 2 | 4 сек |
| 3 | 6 сек |
| 4+ | Polling каждые 30 сек |

### Время

Формат `_timeAgo()`:

| Интервал | Вывод |
|----------|-------|
| < 1 мин | «только что» |
| < 60 мин | «N мин. назад» |
| < 24 ч | «N ч. назад» |
| ≥ 24 ч | «N дн. назад» |
