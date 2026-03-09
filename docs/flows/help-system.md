# Система помощи

Тред-система для диалога ученик ↔ учитель с inline-комментариями к строкам кода и уведомлениями в реальном времени.

---

## Жизненный цикл запроса

```mermaid
stateDiagram-v2
    [*] --> open: Ученик создаёт запрос\nили пишет комментарий
    open --> answered: Учитель отвечает
    answered --> open: Ученик пишет снова
    answered --> resolved: Ученик закрывает
    open --> resolved: Ученик закрывает
    resolved --> open: Ученик пишет\nновый комментарий
    resolved --> [*]
```

**Статусы:**

| Статус | Описание | has_unread_for_teacher | has_unread_for_student |
|--------|----------|----------------------|----------------------|
| `open` | Ожидает ответа учителя | ✅ True | — |
| `answered` | Учитель ответил | — | ✅ True |
| `resolved` | Закрыт учеником | — | — |

---

## Архитектура компонентов

```mermaid
flowchart TB
    subgraph Frontend
        HM[HelpRequestManager\nhelp-requests.js]
        NM[NotificationManager\nnotifications.js]
        CM[CodeMirror\nредактор кода]
    end

    subgraph Backend
        VIEW[help_request_view\nviews.py]
        WS_FUNC["_send_help_ws_notification()"]
        QC[QuizConsumer]
        NC[NotificationConsumer]
    end

    CM -->|"gutterClick"| HM
    HM -->|"POST /help/"| VIEW
    VIEW -->|"channel_layer"| WS_FUNC
    WS_FUNC -->|"group_send\nquiz group"| QC
    WS_FUNC -->|"group_send\nnotifications"| NC
    QC -->|"WS message"| HM
    NC -->|"WS message"| NM
```

---

## Inline-комментарии

Ученик кликает на гutter CodeMirror — открывается тред-виджет для конкретной строки.

```mermaid
flowchart TD
    CLICK[Клик по gutter\nCodeMirror] --> CHECK{Тред уже\nоткрыт?}
    CHECK -->|Да| CLOSE[Закрыть тред]
    CHECK -->|Нет| LOAD{helpData\nзагружены?}
    LOAD -->|Нет| FETCH["GET /help/\n?mark_read=1"]
    FETCH --> CACHE[Кешировать в helpData]
    CACHE --> RENDER
    LOAD -->|Да| RENDER[Создать тред-виджет]

    RENDER --> DOM["DOM:\n— Заголовок 'Строка N'\n— История комментариев\n— Форма ввода"]
    DOM --> WIDGET[Добавить как\nCodeMirror lineWidget]
    WIDGET --> FOCUS[Фокус на textarea]
```

### Структура треда

```
┌──────────────────────────────┐
│ 📌 Строка 5              [✕] │
├──────────────────────────────┤
│ student1 • 10:30             │
│ Не понимаю, почему тут ошибка│
│                              │
│ teacher • 10:45              │
│ Посмотри на тип переменной   │
├──────────────────────────────┤
│ [textarea          ] [→]     │
└──────────────────────────────┘
```

### Line Markers

После загрузки данных, `_updateLineMarkers()` добавляет CSS-класс `line-has-comments` к строкам с комментариями — визуальный индикатор в gutter.

---

## Отправка комментария

```mermaid
sequenceDiagram
    participant U as Ученик
    participant HM as HelpRequestManager
    participant API as help_request_view
    participant DB as Database
    participant WS as _send_help_ws_notification

    U->>HM: Ctrl+Enter или клик "Отправить"
    HM->>HM: Валидация (1-10000 символов)
    HM->>API: POST /quizzes/5/question/3/help/\n{text, line_number, code_snapshot}

    API->>DB: get_or_create HelpRequest
    alt Был resolved
        API->>DB: status = 'open' (переоткрыть)
    end
    API->>DB: Создать HelpComment
    API->>DB: has_unread_for_teacher = True

    API->>WS: _send_help_ws_notification()
    WS->>WS: group_send → notifications_teachers

    API-->>HM: 200 {help_request, comments}
    HM->>HM: Перестроить тред + line markers
```

---

## Уведомления

### Маршрутизация WebSocket уведомлений

```mermaid
flowchart TD
    COMMENT[Новый комментарий] --> WHO{Кто автор?}

    WHO -->|Ученик| TEACHER_NOTIFY["group_send:\nnotifications_teachers\n→ help_notification"]
    TEACHER_NOTIFY --> BADGE_T[Обновить badge\nу всех учителей]

    WHO -->|Учитель| STUDENT_NOTIFY["group_send:\nnotifications_{student_id}\n→ help_notification"]
    STUDENT_NOTIFY --> BADGE_S[Обновить badge\nу ученика]
    WHO -->|Учитель| INLINE["group_send:\nuser_{student}_quiz_{quiz}\n→ help_comment_update"]
    INLINE --> UPDATE[Обновить inline-тред\nесли открыт]
```

### NotificationManager

| Механизм | Когда | Интервал |
|----------|-------|----------|
| WebSocket | Основной | Мгновенно |
| Polling fallback | WS недоступен | 30 секунд |

**Dropdown уведомлений:**

```
┌─ 🔔 3 ─────────────────────────┐
│                                 │
│ Задача 5: Циклы                │
│ Тест: Основы Python            │
│ teacher: Посмотри строку 5...   │
│ 5 мин. назад                    │
│                                 │
│ Задача 2: Строки               │
│ Тест: Строки и списки          │
│ teacher: Правильно, но...       │
│ 2 ч. назад                      │
└─────────────────────────────────┘
```

Клик по уведомлению → `/quizzes/{quiz_id}/?open_help={question_id}#question-{question_id}`

---

## Уникальные ограничения

- **Один запрос на вопрос:** `unique_together = [student, question]` — все комментарии к вопросу в одном треде
- **code_snapshot:** Фиксирует состояние кода на момент комментария — учитель видит контекст
- **Переоткрытие:** Resolved запрос автоматически переоткрывается при новом комментарии
- **mark_read:** GET с `?mark_read=1` сбрасывает флаг `has_unread_for_student`
