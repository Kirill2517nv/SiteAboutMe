# ER-диаграммы

Модели проекта разбиты на 4 домена. Всего **19 моделей** + стандартная модель `User` из Django.

---

## Accounts — Пользователи и группы

```mermaid
erDiagram
    User ||--|| Profile : "has"
    StudentGroup ||--o{ Profile : "contains"

    User {
        int id PK
        string username
        string email
        string password
        bool is_staff
    }

    Profile {
        int id PK
        int user_id FK "OneToOne → User"
        int group_id FK "FK → StudentGroup, nullable"
        bool is_ege "Флаг ЕГЭ-ученика"
    }

    StudentGroup {
        int id PK
        string name "Название группы/класса"
    }
```

!!! info "Связь User ↔ Profile"
    `Profile` расширяет стандартного `User` через `OneToOneField`. Создаётся автоматически при регистрации. Поле `is_ege` определяет доступ к EGE-тренажёру.

---

## Pages — Контент главной и about-страницы

```mermaid
erDiagram
    ContentBlock {
        int id PK
        string page "home | about"
        string block_type "text | image | text_image"
        string title
        text content
        image image
        url link_url
        int order
        string layout "vertical | horizontal | horizontal-reverse"
        string card_bg "CSS цвет фона"
    }
```

!!! note "Content Block Pattern"
    `ContentBlock` — самодостаточная модель без связей. Каждый блок содержит полный набор параметров стилизации: шрифты, цвета, позиционирование, кроп изображений. Аналогичная структура используется в `LessonBlock`.

---

## Lessons — Разделы и уроки

```mermaid
erDiagram
    Section ||--o{ Lesson : "contains"
    Lesson ||--o{ LessonBlock : "has"

    Section {
        int id PK
        string title
        int order
    }

    Lesson {
        int id PK
        int section_id FK "FK → Section, nullable"
        string title
        text description
        file file "Файл урока"
        image preview_image
        string preview_description
        url video_url
    }

    LessonBlock {
        int id PK
        int lesson_id FK "FK → Lesson"
        string block_type "text | image | text_image"
        string title
        text content
        image image
        int order
        string layout
        string card_bg
    }
```

---

## Quizzes — Тесты, вопросы и результаты

Самый крупный домен — **13 моделей**. Разделён на 3 подгруппы для читабельности.

### Структура теста

```mermaid
erDiagram
    Quiz ||--o{ Question : "contains"
    Quiz ||--o{ QuizAssignment : "assigned via"
    QuizAssignment }o--|| StudentGroup : "to group"
    QuizAssignment }o--o| User : "or to user"
    Question ||--o{ Choice : "has"
    Question ||--o{ TestCase : "tested by"
    Question ||--o{ QuestionImage : "illustrated by"
    Question ||--o{ QuestionFile : "attached"

    Quiz {
        int id PK
        string title
        text description
        int max_attempts
        string quiz_type "standard | exam"
        string exam_mode "exam | practice"
        bool is_public
        slug slug
        datetime start_date
        datetime end_date
    }

    QuizAssignment {
        int id PK
        int quiz_id FK
        int group_id FK "nullable"
        int user_id FK "nullable"
        datetime start_date
        datetime end_date
        int max_attempts "переопределяет Quiz.max_attempts"
    }

    Question {
        int id PK
        int quiz_id FK
        string title
        text text
        string question_type "choice | text | code"
        string correct_text_answer
        int ege_number
        string topic
        int points
        json alternative_answers
    }

    Choice {
        int id PK
        int question_id FK
        string text
        bool is_correct
    }

    TestCase {
        int id PK
        int question_id FK
        text input_data
        text output_data
    }

    QuestionImage {
        int id PK
        int question_id FK
        image image
        string alt_text
        int order
    }

    QuestionFile {
        int id PK
        int question_id FK
        file file
        string description
        int order
    }
```

### Результаты и выполнение кода

```mermaid
erDiagram
    User ||--o{ UserResult : "completes"
    Quiz ||--o{ UserResult : "results for"
    UserResult ||--o{ UserAnswer : "contains"
    UserAnswer }o--o| Choice : "selected"
    UserAnswer }o--|| Question : "answers"
    UserAnswer }o--o| CodeSubmission : "linked to"
    User ||--o{ CodeSubmission : "submits"
    Question ||--o{ CodeSubmission : "code for"
    Quiz ||--o{ CodeSubmission : "in quiz"
    UserAnswer ||--o{ SolutionLike : "liked by"
    User ||--o{ SolutionLike : "likes"

    UserResult {
        int id PK
        int user_id FK
        int quiz_id FK
        int score
        datetime date_completed "auto_now_add"
        duration duration
    }

    UserAnswer {
        int id PK
        int user_result_id FK
        int question_id FK
        int choice_id FK "nullable"
        string text_answer
        text code_answer
        text error_log
        bool is_correct
        int submission_id FK "nullable, SET_NULL"
    }

    CodeSubmission {
        int id PK
        int user_id FK
        int question_id FK
        int quiz_id FK
        text code
        string status "pending → running → success/failed/error"
        bool is_correct "nullable"
        text error_log
        string celery_task_id
        datetime created_at
        datetime completed_at
        float cpu_time_ms
        int memory_kb
    }

    SolutionLike {
        int id PK
        int user_id FK
        int answer_id FK
        datetime created_at
    }
```

### Помощь и EGE-прогресс

```mermaid
erDiagram
    User ||--o{ HelpRequest : "asks"
    Question ||--o{ HelpRequest : "about"
    Quiz ||--o{ HelpRequest : "in"
    HelpRequest ||--o{ HelpComment : "discussed in"
    User ||--o{ HelpComment : "writes"
    User ||--o{ ExamTaskProgress : "progresses"
    Quiz ||--o{ ExamTaskProgress : "in exam"
    Question ||--o{ ExamTaskProgress : "on task"
    User ||--o{ SolutionAttachment : "attaches"
    Quiz ||--o{ SolutionAttachment : "for quiz"
    Question ||--o{ SolutionAttachment : "for question"

    HelpRequest {
        int id PK
        int student_id FK
        int question_id FK
        int quiz_id FK
        string status "open | answered | resolved"
        datetime created_at
        datetime updated_at
        bool has_unread_for_teacher
        bool has_unread_for_student
    }

    HelpComment {
        int id PK
        int help_request_id FK
        int author_id FK
        text text "max 10000"
        int line_number "nullable, для inline-комментариев"
        text code_snapshot
        datetime created_at
    }

    ExamTaskProgress {
        int id PK
        int user_id FK
        int quiz_id FK
        int question_id FK
        int time_spent_seconds
        int attempts_to_solve
        bool is_solved
        datetime first_solved_at
        float best_cpu_time_ms
        text best_cpu_code
        int best_memory_kb
        text best_memory_code
    }

    SolutionAttachment {
        int id PK
        int user_id FK
        int quiz_id FK
        int question_id FK
        file file
        text comment
        image image
        datetime created_at
    }
```

---

## Сводная таблица связей

| Связь | Тип | ON_DELETE | Описание |
|-------|-----|----------|----------|
| User → Profile | OneToOne | CASCADE | Расширение пользователя |
| Profile → StudentGroup | FK | SET_NULL | Группа ученика |
| Lesson → Section | FK | SET_NULL | Раздел урока |
| LessonBlock → Lesson | FK | CASCADE | Блоки контента урока |
| Question → Quiz | FK | CASCADE | Вопросы теста |
| QuizAssignment → Quiz | FK | CASCADE | Назначение теста |
| QuizAssignment → StudentGroup | FK | SET_NULL | Назначение группе |
| QuizAssignment → User | FK | SET_NULL | Индивидуальное назначение |
| Choice → Question | FK | CASCADE | Варианты ответа |
| TestCase → Question | FK | CASCADE | Тест-кейсы для кода |
| UserResult → User, Quiz | FK | CASCADE | Результат прохождения |
| UserAnswer → UserResult | FK | CASCADE | Ответ на вопрос |
| UserAnswer → CodeSubmission | FK | SET_NULL | Связь с посылкой кода |
| CodeSubmission → User, Question, Quiz | FK | CASCADE | Посылка кода |
| HelpRequest → User, Question, Quiz | FK | CASCADE | Запрос помощи |
| HelpComment → HelpRequest, User | FK | CASCADE | Комментарий |
| ExamTaskProgress → User, Quiz, Question | FK | CASCADE | Прогресс EGE |
| SolutionAttachment → User, Quiz, Question | FK | CASCADE | Прикрепление решения |
| SolutionLike → User, UserAnswer | FK | CASCADE | Лайк решения |

!!! warning "Уникальные ограничения"
    - `HelpRequest`: `unique_together = [student, question]` — один запрос на вопрос
    - `ExamTaskProgress`: `unique_together = [user, quiz, question]` — один прогресс на задачу
    - `SolutionAttachment`: `unique_together = [user, quiz, question]` — одно прикрепление на задачу
    - `SolutionLike`: `UniqueConstraint(user, answer)` — один лайк на ответ
