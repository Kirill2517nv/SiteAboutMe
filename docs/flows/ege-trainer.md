# EGE Тренажёр

Режим подготовки к ЕГЭ по информатике с двумя режимами: экзамен и практика.

---

## Два режима работы

```mermaid
flowchart LR
    subgraph EXAM["Режим экзамена"]
        direction TB
        E1[Одна попытка]
        E2[Таймер обратного отсчёта]
        E3["Проверка только\nпри завершении"]
        E4[Линейная навигация]
    end

    subgraph PRACTICE["Режим практики"]
        direction TB
        P1[Без ограничений]
        P2[Таймер прямого отсчёта]
        P3["Мгновенная проверка\n/check/"]
        P4[Свободная навигация]
    end

    QUIZ[Quiz\nexam_mode] -->|exam| EXAM
    QUIZ -->|practice| PRACTICE
```

---

## Общий flow

```mermaid
flowchart TD
    LIST[GET /ege/\nСписок вариантов] --> DETAIL[GET /ege/id/\nДетали варианта]
    DETAIL --> MODE{exam_mode?}

    MODE -->|exam| EXAM_CHECK{UserResult\nуже есть?}
    EXAM_CHECK -->|Да| RESULT[redirect → /ege/id/result/]
    EXAM_CHECK -->|Нет| SOLVE

    MODE -->|practice| SOLVE[Решение задач]

    SOLVE --> TASK_TYPE{question_type?}

    TASK_TYPE -->|text| TEXT_FLOW
    TASK_TYPE -->|code| CODE_FLOW

    subgraph TEXT_FLOW[Текстовые задачи]
        direction TB
        T1[Ввести ответ] --> T2{Practice mode?}
        T2 -->|Да| T3["POST /check/\nМгновенная проверка"]
        T3 --> T4[Обновить ExamTaskProgress\nattempts, is_solved]
        T2 -->|Нет| T5[Ответ сохранён\nлокально]
    end

    subgraph CODE_FLOW[Задачи на код]
        direction TB
        C1[Написать код] --> C2["POST /submit/\nАсинхронная проверка"]
        C2 --> C3[Celery + Docker]
        C3 --> C4[WebSocket результат]
        C4 --> C5[Обновить ExamTaskProgress\nbest metrics]
    end

    TEXT_FLOW --> SAVE_TIME["POST /save-time/\nПериодическое сохранение"]
    CODE_FLOW --> SAVE_TIME

    SAVE_TIME --> FINISH["POST /ege/id/finish/\nЗавершить вариант"]
    FINISH --> SCORE[Подсчёт баллов\nsum question.points]
    SCORE --> RESULT_PAGE[GET /ege/id/result/\nСтраница результата]
```

---

## ExamTaskProgress — Отслеживание прогресса

Модель хранит прогресс по каждой задаче для каждого ученика.

```mermaid
flowchart TD
    ATTEMPT[Попытка решения] --> PROGRESS[get_or_create\nExamTaskProgress]
    PROGRESS --> INC[attempts_to_solve += 1]
    INC --> CORRECT{Ответ правильный?}

    CORRECT -->|Нет| SAVE[Сохранить\ntime_spent]
    CORRECT -->|Да| SOLVED{Уже is_solved?}

    SOLVED -->|Нет| MARK["is_solved = True\nfirst_solved_at = now()"]
    SOLVED -->|Да| METRICS{Метрики лучше\nпредыдущих?}

    MARK --> METRICS
    METRICS -->|CPU лучше| BEST_CPU["best_cpu_time_ms = X\nbest_cpu_code = code"]
    METRICS -->|Память лучше| BEST_MEM["best_memory_kb = Y\nbest_memory_code = code"]
    METRICS -->|Нет| SAVE
    BEST_CPU --> SAVE
    BEST_MEM --> SAVE
```

### Хранимые метрики

| Метрика | Описание | Обновление |
|---------|----------|------------|
| `time_spent_seconds` | Общее время на задачу | При каждом save-time |
| `attempts_to_solve` | Количество попыток | При каждой проверке |
| `is_solved` | Решена ли задача | При первом правильном ответе |
| `first_solved_at` | Когда решена впервые | Однократно |
| `best_cpu_time_ms` | Лучшее время CPU | Если лучше предыдущего |
| `best_cpu_code` | Код лучшего по CPU | Вместе с best_cpu_time_ms |
| `best_memory_kb` | Лучшее использование RAM | Если лучше предыдущего |
| `best_memory_code` | Код лучшего по памяти | Вместе с best_memory_kb |

---

## Проверка текстового ответа (Practice)

```mermaid
sequenceDiagram
    participant U as Ученик
    participant JS as Alpine.js
    participant API as ege_check_answer_view
    participant DB as Database

    U->>JS: Ввести ответ + Enter
    JS->>API: POST /ege/5/check/\n{question_id: 1, answer: "42"}

    API->>API: normalize_text_answer("42")
    API->>DB: Question.check_text_answer()

    alt correct_text_answer совпадает
        API->>API: is_correct = True
    else alternative_answers содержит
        API->>API: is_correct = True
    else
        API->>API: is_correct = False
    end

    API->>DB: get_or_create ExamTaskProgress
    API->>DB: attempts += 1
    alt Правильно и не solved
        API->>DB: is_solved = True
    end

    API-->>JS: {is_correct, attempts, is_solved}
    JS->>U: Визуальная обратная связь\n✅ или ❌
```

---

## Завершение варианта

```mermaid
flowchart TD
    FINISH["POST /ege/id/finish/"] --> EXAM_MODE{exam_mode?}

    EXAM_MODE -->|exam| EXISTS{UserResult\nуже существует?}
    EXISTS -->|Да| DENY[403: уже сдан]
    EXISTS -->|Нет| PROCESS

    EXAM_MODE -->|practice| PROCESS[Обработать ответы]

    PROCESS --> DURATION[Вычислить duration\nиз session]
    DURATION --> RESULT[Создать UserResult]
    RESULT --> LOOP[Для каждого вопроса]

    LOOP --> QTYPE{Тип?}
    QTYPE -->|text| CHECK_TEXT[check_text_answer\n→ score += points]
    QTYPE -->|code| CHECK_CODE[Последний CodeSubmission\n→ is_correct? → score += points]

    CHECK_TEXT --> ANSWER[Создать UserAnswer]
    CHECK_CODE --> ANSWER
    ANSWER --> NEXT{Ещё?}
    NEXT -->|Да| LOOP
    NEXT -->|Нет| UPDATE_PROGRESS[Обновить ExamTaskProgress\nдля правильных ответов]
    UPDATE_PROGRESS --> RESPONSE["JSON:\nscore, total_points,\npending_checks,\nredirect_url"]
```

---

## Дополнительные функции

### Прикрепление решений

`POST /ege/<id>/task/<num>/upload-attachment/` — загрузка файла или скриншота решения.

- `SolutionAttachment` с `unique_together = [user, quiz, question]`
- Повторная загрузка обновляет существующее прикрепление

### Просмотр решений

`GET /ege/<id>/task/<num>/solution/<user_id>/` — просмотр решения ученика.

Доступно автору и staff. Показывает код, прикреплённые файлы, метрики.

### Лайки решений

`POST /ege/solutions/<answer_id>/like/` — toggle лайка.

- `SolutionLike` с `UniqueConstraint(user, answer)`
- Повторный запрос убирает лайк
- Отображается в профиле ученика (`likes_received`)

---

## Сохранение времени

Фронтенд периодически отправляет `POST /ege/<id>/save-time/` с текущим `time_spent` для активной задачи. Это обеспечивает сохранение прогресса даже при закрытии вкладки.

```json
{"question_id": 1, "time_spent": 120}
```

Значение **перезаписывает** `ExamTaskProgress.time_spent_seconds` (не инкрементирует).
