# Quiz Flow

Полный цикл работы с тестами: назначение, контроль доступа, прохождение, подсчёт баллов.

---

## Каскад назначений (Assignment Cascade)

Система определяет доступ к тесту через `get_effective_quiz_settings()`:

```mermaid
flowchart TD
    START[Запрос доступа к Quiz] --> IND{Есть индивидуальное\nназначение?}
    IND -->|Да| USE_IND[Использовать\nQuizAssignment user]
    IND -->|Нет| GRP{Есть групповое\nназначение?}
    GRP -->|Да| USE_GRP[Использовать\nQuizAssignment group]
    GRP -->|Нет| PUB{Quiz is_public?}
    PUB -->|Да| USE_QUIZ[Использовать\nнастройки Quiz]
    PUB -->|Нет| SU{Пользователь\nsuperuser?}
    SU -->|Да| USE_QUIZ
    SU -->|Нет| DENY[Доступ запрещён\nredirect → quiz_list]

    USE_IND --> MERGE[Объединить настройки]
    USE_GRP --> MERGE
    USE_QUIZ --> MERGE

    MERGE --> |"start_date: assignment ∥ quiz\nend_date: assignment ∥ quiz\nmax_attempts: assignment ∥ quiz"| ACCESS[Настройки доступа готовы]
```

**Приоритет полей:** Если в `QuizAssignment` заполнены `start_date`, `end_date` или `max_attempts` — они переопределяют аналогичные поля `Quiz`. Иначе берутся из `Quiz`.

---

## Контроль доступа

```mermaid
flowchart TD
    REQ[GET /quizzes/id/] --> SETTINGS{get_effective_quiz_settings}
    SETTINGS -->|None| DENY[redirect → quiz_list]
    SETTINGS -->|OK| TIME_START{now < start_date?}
    TIME_START -->|Да| NOT_STARTED[redirect: тест ещё не начался]
    TIME_START -->|Нет| TIME_END{now > end_date?}
    TIME_END -->|Да, GET| READ_ONLY[Показать в режиме\nтолько чтение]
    TIME_END -->|Да, POST| EXPIRED[redirect: время вышло]
    TIME_END -->|Нет| ATTEMPTS{max_attempts > 0?}
    ATTEMPTS -->|Да| COUNT{attempts_count\n>= max_attempts?}
    COUNT -->|Да| LIMIT[redirect: попытки исчерпаны]
    COUNT -->|Нет| ACTIVE[Активный режим]
    ATTEMPTS -->|Нет (безлимит)| ACTIVE
```

### Read-Only режим

Когда тест завершён (`end_date` прошёл), ученик может просмотреть свои лучшие ответы:

- Для каждого вопроса выбирается лучший `UserAnswer` (правильный предпочтительнее)
- Код восстанавливается из `code_answer` или связанного `CodeSubmission`
- Нельзя отправлять новые ответы

---

## Прохождение теста

### GET — Загрузка вопросов

```mermaid
flowchart TD
    LOAD[Загрузка Quiz + Questions] --> SOLVED{Найти уже решённые\nвопросы}
    SOLVED --> FILTER[Исключить решённые\nиз списка]
    FILTER --> CODE{Есть code-вопросы?}
    CODE -->|Да| RESTORE[Восстановить код\nиз последней неудачной\nпопытки]
    CODE --> SUBMISSIONS[Загрузить последние\nCodeSubmission + метрики]
    RESTORE --> JSON[Сформировать tasks_json]
    SUBMISSIONS --> JSON
    CODE -->|Нет| JSON
    JSON --> SESSION[Сохранить quiz_start_time\nв session]
    SESSION --> RENDER[Отрендерить quiz_detail.html]
```

### POST — Отправка ответов

```mermaid
flowchart TD
    POST[POST /quizzes/id/] --> DURATION[Вычислить duration\nиз session start_time]
    DURATION --> RESULT[Создать UserResult\nscore=0]
    RESULT --> LOOP[Обработать каждый вопрос]

    LOOP --> TYPE{question_type?}
    TYPE -->|choice| CHOICE[Проверить\nChoice.is_correct]
    TYPE -->|text| TEXT[normalize_text_answer\n+ сравнить]
    TYPE -->|code| DOCKER[Запустить в Docker\nпротив TestCase]

    CHOICE --> ANSWER[Создать UserAnswer\nis_correct=True/False]
    TEXT --> ANSWER
    DOCKER --> ANSWER

    ANSWER --> NEXT{Ещё вопросы?}
    NEXT -->|Да| LOOP
    NEXT -->|Нет| BULK[bulk_create UserAnswer]
    BULK --> SCORE[score = текущие +\nранее решённые]
    SCORE --> UPDATE[Обновить\nUserResult.score]
    UPDATE --> RENDER[quiz_result.html\nс failed_answers]
```

---

## Подсчёт баллов

### Standard Quiz
Балл = количество уникальных правильно отвеченных вопросов за все попытки.
Уже решённые вопросы не показываются повторно.

### Exam Quiz
Балл = сумма `question.points` для правильных ответов.
Каждый вопрос может иметь разный вес (1-2 балла в ЕГЭ).

---

## Финализация через API

`POST /quizzes/<id>/finish/` — альтернативный путь (из Alpine.js фронтенда):

```mermaid
flowchart TD
    FINISH[POST /finish/] --> PENDING{Есть pending\nCodeSubmission?}
    PENDING -->|Да, force=false| CONFLICT[409: pending_questions]
    PENDING -->|Да, force=true| PROCEED[Продолжить\nс текущими результатами]
    PENDING -->|Нет| PROCEED
    PROCEED --> SOLVED[Загрузить ранее\nрешённые вопросы]
    SOLVED --> PROCESS[Обработать ответы\nиз JSON body]
    PROCESS --> RESULT[Создать UserResult\n+ UserAnswer]
    RESULT --> RESPONSE["JSON: score, total,\nfailed_questions,\npending_checks"]
```

!!! tip "Паттерн force/pending"
    Если ученик нажал «Завершить», но код ещё проверяется — фронтенд получит 409 и покажет предупреждение. Повторный запрос с `force=true` завершит тест, используя последний доступный результат каждой посылки.
