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
python manage.py load_ege <file.json>    # Import EGE variant or question bank (fixtures/ege_bank_template.json)
python manage.py seed_ege_tasks          # 27 EgeTask records + theory article stubs
python manage.py seed_ege_theory_17      # Fill one EGE theory article (one command per task)
python manage.py recalc_ege_difficulty --dry-run   # Recompute Question.solve_rate from real success rate
python manage.py retag_ege --from 2 --to 5 --dry-run   # Codifier changed: move/archive/delete questions of one EGE task
python manage.py mark_exam_pool --dry-run              # Fill the exam-only reserve (Question.exam_only)
python manage.py ege_pools --dump fixtures/ege-pools.json   # Snapshot pools + EgeTask settings (dev → prod, see docs/ege-bank-deploy.md)
python manage.py ege_pools --load fixtures/ege-pools.json --dry-run
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

- **accounts** – User auth, `Profile` (extends User with group assignment, `is_ege` flag), `StudentGroup` for organizing students into classes. `ProfileView` shows one stat block, **Учебник** (per-`Section` grades, lessons read, practicum tasks, reading time, «что подтянуть» – via `textbook.services.profile_textbook_stats`); every EGE number lives on the trainer's «Мой прогресс» tab instead, so the two never disagree. Superusers open any student's profile at `accounts:student_profile` (`profile/<user_id>/`); students get 403 on foreign profiles. `templatetags/profile_tags.py` provides the `duration_display` filter for timedelta formatting.
- **pages** – Home/about pages built from `ContentBlock` models with rich styling (fonts, colors, image crop/positioning)
- **lessons** – `Section` → `Lesson` → `LessonAttachment` / `LessonBlock` hierarchy. `LessonAttachment` stores multiple downloadable files per lesson. `Lesson` supports Slidev presentations (`presentation_url`, `presentation_title`, `presentation_pdf`) and video URLs. All file uploads use a unified path `media/lessons/{safe_title}/`. File downloads use Nginx X-Accel-Redirect in production. Dev server serves media with `index.html` fallback for Slidev SPA.
- **quizzes** – `Quiz` with time-based access windows, `Question` (multiple choice, free text, Python code execution with `TestCase` validation, `title` field), `QuizAssignment` (to groups or individuals), `UserResult`/`UserAnswer` for tracking. Attempt limiting with override support. `CodeSubmission` for async code execution results.

**EGE Trainer** (`quizzes` app, mounted at `/ege/`, urls in `urls_ege.py`). **Wording:** mode `study` is called «Тренировка» everywhere in the UI (the DB value stays `study`); «Учёба» is gone. The unlock counter counts *distinct* questions and the stats block counts *answers* – label them so the two numbers are never read as the same thing:
- **Hub `/ege/`** – three tabs: map of all 27 EGE tasks, ready-made variants, personal progress. The progress tab (`_ege_progress.html`, fed by `ege_stats.overview`) is split into two sections on purpose, named with the same words as the hub's tabs: **Задания** (`predicted_score` forecast, weak spots, per-task table – everything from `PracticeItem`) and **Варианты** (`ege_stats.variant_summary` – `variant_forecast`, per-variant bars, pace per number). The two are never added together: one task solved in a session and a whole 235-minute variant measure different things. Each section opens with a forecast card, and both cards are the same partial (`_ege_forecast.html`) because they measure the same thing – the exam score – differing only in where it came from: assembled from single tasks on the left, taken off a whole paper on the right. The variant forecast is the **last** written paper, not an average: the first variant was written knowing half the topics, and averaging it in would drag the forecast down long after those topics were learned
- **Table tooltips are `data-tip`, not `title`** – `_ege_progress.html` hosts one Alpine tooltip for the whole block (the dark box the weekly-dynamics bars already use); cells carry only `data-tip="…"` and `cursor-help`, and delegated `mouseover`/`mouseleave` on the wrapper find the cell via `closest('[data-tip]')`. The tooltip is `position: fixed` because the tables sit inside `overflow-x-auto`, which would clip an absolutely positioned one on the first row and the edge columns; its `:style` is an **object**, since Alpine's string form does `setAttribute('style', …)` and would wipe the `display:none` that `x-show` sets. That is why the column captions above the tables are gone: a full sentence fits in a tooltip, a legend line never did
- **A guest sees the progress tab filled with an example** – `ege_stats.demo_overview()` builds an `overview`-shaped dict for an invented student (`DEMO_ACCURACY`, one exam accuracy per task; everything else – forecast, weak spots, table, variants – is derived from it by the same formulas the real statistics use, so the forecast card never contradicts the table under it). `ege_list_view` merges it into the context for anonymous visitors, and `_ege_progress.html` renders unchanged; the «это пример» banner and the login CTA live in `ege_list.html` above the include, because the same partial also draws a real student's progress and the teacher report. Demo variant rows are `SimpleNamespace` with `id=None` – that is what tells `_ege_variant_group.html` not to build a link. **The hub's top summary strip stays authenticated-only**: invented numbers belong inside the labelled tab, not at the top of the page
- **Variants are split by mode exactly like tasks** – `Quiz.exam_mode` reaches the query itself through `ege_stats.variant_ids(mode)`, and `VARIANT_MODES` is the one place the two naming systems meet (stats say `study`/`exam` like a practice session; the DB says `practice`/`exam`). `variant_summary` returns a `study` and an `exam` bucket, never a total, and `variant_by_number` gives each number a study and an exam column – a task drilled for 20 minutes with the theory open must not colour the exam pace. A row appears once the student has *attempted* the number (an `ExamTaskProgress` row, solved or not), mirroring `mode_task_table`. **The forecast is exam-only**: `variant_forecast` reads `exam_variant_ids()`, because a variant written with no timer and any number of attempts would promise a score the real exam will not give. Switching a variant to «Экзамен» in the admin is what makes it count toward the forecast
- **Task card `/ege/task/<N>/`** – theory articles for that task + personal stats + practice session launcher
- **Practice sessions** – `PracticeSession` / `PracticeItem` (`models.py`). A short batch of questions picked from the bank. One mechanism covers three scenarios, differing only in the picking rule (`kind`): `topic` (by EGE task number), `mistakes` (questions whose *last* attempt failed), `mixed`. Two modes (`mode`): `study` checks each answer immediately, `exam` stays silent until the result page. **Correct answers are never serialized into the page** (superusers get the same amber «Показать ответ» panel as on `ege_detail`, rendered server-side, so the page data stays clean for every role).** In `study` a wrong answer only says so – the student may retry, and `PracticeItem.attempts` records which attempt succeeded. The answer is handed out solely by `practice_reveal_view` («Показать ответ»), which sets `gave_up` and closes the task as unsolved; `PracticeItem.is_locked` then rejects further answers (409). `recalc_ege_difficulty` counts only first-attempt successes, so retries don't inflate `solve_rate`. In `exam` there is no check button at all: answers autosave (on blur, on navigation, before finishing), stay editable until the session ends, and neither the save response nor the page payload carries the outcome. An exam also has a hard hour: `PracticeSession.deadline` = `created_at + EXAM_MINUTES`, the page counts down and finishes itself, and `_owned_session` closes an expired exam server-side (stamping `finished_at` with the deadline, not «now»). **The result page is finished-sessions-only**: `practice_result_view` redirects a running session back to `/ege/practice/<pk>/`. It prints the correct answer under every task the student got wrong, and exam answers stay editable to the last second - so a second tab on `/result/` was the whole «answers never reach the browser» design undone, and in `study` it handed out the answer without the `gave_up` price.
- **Solved questions are never served again** – `exclude_solved()` drops a correctly solved question from every study pick and from `available_counts`, *except* `question_type='code'`: the same algorithm can be rewritten faster or leaner, so a code task may come back (last, oldest-first) and can be retried on purpose from the archive. `/ege/task/<N>/solved/` lists the student's solved questions with their own answer or code (plus cpu/memory of the submission) and the «Переписать решение» button (`ege:ege_practice_retry`, code only, `build_retry_session`). A retry runs in its own session `kind='retry'`, which is **not graded**: `update_practice_item_from_submission` only ever writes a success there (a failed experiment leaves `is_correct=None`, so the task stays solved and out of the mistake pool), `PracticeItem.is_locked` is always False so variants can be fired one after another, and `EXCLUDED_KINDS` keeps the whole session out of statistics and out of the exam-unlock count. Records come from `best_code_metrics()` – `Min(cpu_time_ms)` and `Min(memory_kb)` over the student's *correct* submissions, so the fastest and the leanest run may be different attempts
- `ege_practice.py` – question picking and session sizing. **Study and exam size differ by design**: study = 45 min by the per-task norm but never more than `STUDY_DEFAULT_SIZE` = 8 by default (short tasks hit the cap, task 17 → 3, task 27 → 1) – a student can still type any number up to 30; exam = fits in 60 min and never exceeds 5, unless `EgeTask.exam_size` overrides it (per task, editable in the admin list, empty = by the norm). The norm describes an average question of that number; a bank of hard ones needs fewer, and a hand-set number is not clipped by `EXAM_MAX_SIZE` – the teacher set it on purpose. Also: difficulty mix (`mix={1: 2, 3: 2}`), mistake pool
- **Exam is locked until the topic is worked through** – `EgeTask.exam_unlock_threshold` (per task, editable in the admin list, default 10) is how many *distinct* questions of that task must be solved correctly in `study` mode before `exam` mode opens. `ege_practice.exam_access()` returns `(open, solved, threshold)`; the form hides the exam button and `practice_start_view` refuses the POST. Exam-mode solving never counts toward the threshold
- **Classroom pool** – `Question.classroom_only` is a separate set for a lesson: `pick_classroom_questions()` returns **all** of them ordered by id (the teacher decides how many), so «task 3» is the same question for every student in the room, and `bank_queryset` hides it from study and exam alike. Session `kind='classroom'` (always `mode='study'`). `EgeTask.classroom_enabled` is the teacher's switch: while it is off, students see no button and a direct POST is refused. Superusers flip it from the task card itself (`ege:ege_classroom_toggle`), not only from the admin – it is pulled before every lesson. **Classroom work is excluded from every statistic** (`ege_stats` filters out `session__kind='classroom'`) and from the exam-unlock threshold – these questions are worked through together at the board, so they measure the lesson, not the student. Fill the pool with `mark_exam_pool --pool classroom`, the admin checkbox, or the bank page below
- **Teacher's view of a student** – `/ege/?student=<id>` renders the same hub with that student's numbers (`views._viewed_student`, superusers only, the same rule as a foreign profile in `accounts.ProfileView`). No separate template on purpose: a second layout of the same figures is a second place for them to drift. The mistakes card loses its form there – pressing it would start the *teacher's* own mistake session with the student's count on the button. The teacher bar (`_ege_teacher_bar.html`, shared with the class page) repeats the profile's switcher, because it is the same mode of work
- **Class table `/ege/class/`** (`ege_class_view`, superusers only) – one row per student, one section per `StudentGroup`, sorted by forecast descending inside a class: the table is read from the top and the ones who fell behind must not hide in the middle of the alphabet. Columns are what a lesson is planned by – the forecast assembled from single tasks and how many tasks it rests on, the score of the last exam variant (the same pair of forecasts as `_ege_forecast.html`, both out of 100), the mistake debt, the three most expensive gaps, and the hub's weekly-dynamics graph; the date of the last session sits under the name. The debt is a link to `/ege/student/<id>/mistakes/` (`ege_student_mistakes_view`) – the same set of questions the student would get from «Работа над ошибками», in read-only: the condition rendered in full, the student's own answer or code (with the error log), and the teacher's amber «Показать ответ» panel. It is not a session and must not be: a session's questions are picked at start and land in the statistics of whoever started it. Its selection repeats `mistake_count` literally, because the counter in the table links to it and the two numbers have to agree. Study-vs-exam accuracy columns were tried and dropped: the teacher collapsed the two percentages into «where are the holes» anyway, and the debt and the weak-task chips answer that with the task numbers themselves. One class is shown at a time (`?group=<id>`, tabs above the table, default the first class; `all` and `none` are their own tabs) – with many classes a page of five tables stops answering its one question. The dynamics graph deviates from the personal page twice on purpose: `_class_dynamics` scales bar heights against the **class** peak, not each student's own (a table is read across rows), and shows 4 weeks instead of 8 – eight triples of bars inside a table row are hatching, not a graph. A week runs Monday to Sunday (`day - timedelta(days=day.weekday())`); the caption under a bar group is that Monday, the tooltip carries the whole span. Tooltips are the fixed-position Alpine ones from `_ege_progress.html`, for the same reason: `overflow-x-auto` would clip an absolutely positioned one. `ege_stats.class_rows(users)` counts the whole class in seven queries instead of calling `overview()` per student (which would be ~500 queries a page), and repeats the personal page's formulas literally – accuracy is rounded to a percent before it is multiplied by the task's point value, exactly as `predicted_score` does – because the teacher keeps the table and the student's own page open side by side. One deliberate difference: «что подтянуть» lists only tasks the student has attempted; untouched topics are a study plan on the personal page, but in a class table they would fill a beginner's whole row
- **Bank page `/ege/task/<N>/bank/`** (`ege_bank_view`, superusers only) – the whole bank of one task with the condition rendered in full and one radio group per question: тренировка (default) / в классе / экзамен. It exists because the admin list shows titles, while the decision is made by reading the problem. The three pools are the two flags `classroom_only` / `exam_only`, so it is the same data the admin edits – one form for the page, saved by `bulk_update`. The condition is rendered by `_ege_question_body.html` – the **same partial** the student's session card uses (`ege_practice.html`, plus the solved archive and the mistakes page), so the bank page doubles as proofreading: raw LaTeX left by the parser, a table that fell apart, a lost image look here exactly as the student will see them. MathJax now loads on every page that shows a condition – `_mathjax.html`, one config for the variant page, the session, the attempt review, the bank, the solved archive and the mistakes page. It used to be a copy of the same `window.MathJax` block in four templates, and the practice session simply never got one: the student read `\(F = 
eg x\)` as raw text while the same question on a variant page rendered fine. The teacher's answer panel is `_ege_answer_body.html`, also one file for the session, the bank and the mistakes page: two of the three copies read `tc.expected_output` while the field is `TestCase.output_data`, and Django renders an unknown attribute as an empty string – the panel showed an empty box for every code task, which read as «the question has no answer». For a code task the answer *is* the expected output (task 2 prints `zyxw`); there is no separate `correct_text_answer` on those. `QuestionRenderTests` guards all of it – one MathJax config per page, the bank's condition markup byte-identical to the session's, and the expected output visible to the teacher on all three pages and to no student. It shows questions from **all three** pools (`bank_queryset(include_exam_only=True, include_classroom=True)`), otherwise a question moved into the reserve could never be moved back. A **group moves whole**: touching task 20 of a 19–21 trio carries 19 and 21 with it, since the trio is always served together, and the linked page shows all three numbers like the task card does
- **Exam reserve** – `Question.exam_only` marks questions hidden from study sessions so the exam checks knowledge of the topic rather than memory of drilled tasks. `mark_exam_pool` fills it (never more than half a task's bank). Exam picking order: unseen reserve → long-unseen common questions → seen reserve. Exam composition is not user-selectable: `size` and `mix` from the form are ignored in exam mode
- `ege_stats.py` – all EGE analytics in one place: per-mode stats (`mode_rows` – study vs exam accuracy, session counts and `exam['last']`, the result of the most recent finished exam, which is what the task card shows: an average dragged down by the very first exam says nothing about readiness, kept apart because low study accuracy is a normal stage, not a readiness signal; an unfinished exam does not count as passed), accuracy per task, **`predicted_score` – exam-only**: `EGE_TASK_POINTS[n] × exam accuracy`, plus the sum of average exam times as the projected minutes against the 235-minute limit. A task with no exam contributes neither points nor minutes (no норматив substitution): training accuracy must not be promoted into a forecast, and the old `pace()` was removed with the split card. Also: weak tasks weighted by point value, weekly dynamics, pace vs 235 min, streak, theory coverage, and `mode_task_table` – the study/exam split per EGE task for the «По каждому заданию» table on the progress tab (only tasks the student has attempted). Shared by the hub, the profile and the teacher report – the numbers must match everywhere
- **The task card counts tasks, not attempts** – `task_stats` returns `solved` / `bank_size` / `first_try` / `progress` from `_solved_by_number` (distinct questions of that bank the student has solved in practice, and how many of them fell on the first attempt – `PracticeItem.attempts <= 1`, where `0` means a row older than the field). The card reads «решено X из Y» plus «N с первой попытки»; how many times someone pressed «Проверить» belongs on `/ege/task/<N>/solved/`, which already shows the attempt of each solved task. `accuracy` (correct ÷ attempts) stays in the dict but is no longer displayed – `weak_tasks` ranks by it. `_practice_by_number` is practice-only: variant work never merges into the per-task numbers (it has its own `variant_summary`), which is why a task with an empty bank now reads «нет задач» instead of «0/1» left over from a variant
- **Tasks 26 and 27 are scored 0/1/2**, not right/wrong – `ege_scoring.py` (`grade()`), the only place that knows the ФИПИ partial-credit rules. Since the 2027 КИМ both tasks share one rule: the answer is two numbers, and 1 point is given when they are swapped or only one cell is right (before 2027 task 27 answered with two rows of two numbers and had a rule of its own – questions imported in that format keep working, but are graded by exact match, with no partial credit, until the bank is re-imported). Comparison is done on the *numbers*, not on the text of the output, so `43656 36` and the same pair on two lines are one answer. The point lands in `CodeSubmission.score` / `PracticeItem.score` / `UserAnswer.score` / `ExamTaskProgress.score` (`null` everywhere else – the field exists only where the score is partial). A partial score **does not solve the task**: it stays in the mistake pool and is served again, but statistics count it as half a correct answer (`PRACTICE_CREDIT` / `PROGRESS_CREDIT` in `ege_stats`), and a variant's primary score gets the real point. `check_code_task` therefore runs *all* tests for these two tasks instead of stopping at the first failure, and takes the worst one
- `ege_constants.py` – `EGE_SCORE_CONVERSION`, `EGE_RECOMMENDED_TIME`, `EGE_TASK_POINTS`, `EGE_CODE_TASKS`, `ege_time_color()`. Separate module because `views`, `ege_practice`, `ege_stats` and `accounts` all need them. `EGE_RECOMMENDED_TIME` follows the 2027 spec appendix and sums to exactly 235 minutes; it alone drives session size, time colouring and the projected minutes, so a codifier change is one edit here
- **Variants and practice are two separate pools** – `bank_queryset` (and with it every pick, the mistake counter, the classroom set, the exam reserve and `available_counts`) reads `PRACTICE_QUIZ_TYPES = ('bank',)`: a question sitting inside an assembled variant is never served in a practice session. Before the split it was, and one question was counted two different ways – working through a variant silently drained the practice pool of all 27 tasks, while the exam-unlock counter (`study_solved_count`, study sessions only) did not move at all. A variant measures the whole 235-minute paper; practice measures one topic. `_solved_question_ids` is therefore practice-only too – mixing `ExamTaskProgress` in made the task card claim more solved questions than the bank holds. `EGE_QUIZ_TYPES = ('exam', 'bank')` stays what statistics and the admin commands (`retag_ege`, `mark_exam_pool`) filter on: past answers count wherever they were given, and only the archive (`quiz_type='standard'`) drops out
- **Linked questions (19–21)** – `Question.group_id` / `group_order` tie a set of questions that cannot be served apart: task 19 states the game, tasks 20 and 21 open with «Для игры, описанной в задании 19». `ege_practice.expand_groups`, called once in `build_session`, pulls the whole group in `group_order` for every scenario (topic, mistakes, mixed, exam, classroom) – including members the student already solved, since without task 19 the other two are unsolvable. The requested size is trimmed by whole groups, never mid-group, and one group always gets through. `mark_exam_pool` skips grouped questions entirely (`group_id=''`): the flag sits on one question but the group is served whole, so a reserved task 19 would leak into practice alongside task 20. Statistics are unaffected – each question still counts under its own `ege_number`. The whole trio lives in one bank file (`fixtures/bank-19-21.json`); format in `docs/ege-bank-format.md`. **One page for the trio**: `/ege/task/20/` and `/21/` redirect to `/ege/task/19/`, which is badged «19-21», titled `LINKED_GROUP_TITLE` («Теория игр»), carries the theory of all three and shows a separate stats card per number (the map's `page_number` sends all three cards there). The start form counts **triples**, not questions – `practice_start_view` multiplies by `group_span` – and the manual difficulty mix is hidden, since a triple is served whole. The trio is answered with **code** (`EGE_CODE_TASKS` covers 19–21), so a solved triple can come back and `build_retry_session` expands the group too – the retried question stays open, its neighbours arrive carried. Output checking goes through `ege_scoring.outputs_match` (used by both the Celery and the synchronous path): when the expected output is nothing but numbers, the numbers are compared in order, so task 20's two numbers pass on one line or two; anything else falls back to normalized text. **`PracticeItem.carried`**: a group member the student already solved comes back prefilled with the previous answer, locked and flagged, so mistake work fixes only what was wrong; carried rows are excluded from every statistic, from the mistake pool and from the exam-unlock count. The navigator's rows are computed server-side (`views_practice._navigator_rows`): a group gets its own framed row, everything else rows of four – a mixed mistake session would otherwise misalign. The group cap never trims a mistake session: `build_session` sets `cap` per scenario, and for mistakes and classroom it is None, so the debt is served whole
- **Question bank** – `Quiz(quiz_type='bank')` holds a themed batch imported from kompege.ru. Not a separate model: variant listings filter on `quiz_type='exam'`, so banks never show up there. Each EGE task needs its own bank – a number that only appears inside variants has an empty practice pool. Banks are created as `is_public=True, exam_mode='practice'` so code submission passes the existing access check. **JSON format spec for the external parser: `docs/ege-bank-format.md`** (dedup by `external_id`, `[img:N]`/`[sup:]`/tab-table markup, media paths)
- **Difficulty is hybrid** – `Question.difficulty` comes from the import, `Question.solve_rate` is recomputed from actual first-attempt success by `recalc_ege_difficulty` (daily via Celery Beat). `Question.effective_difficulty()` prefers the statistic; the same thresholds are mirrored in SQL by `ege_practice.effective_difficulty_expr()`
- **Theory** – `textbook.EgeTask` (1–27) + `Article(track='ege')`. Article template and writing rules: `docs/ege-theory-brief.md`
- **Projector mode** (`static/js/present-mode.js` + `templates/_present_mode.html` / `_present_button.html`) – a task shown on the classroom projector: native fullscreen, the chrome hidden (`present-hide`), the text scaled by the **root font-size**, since the whole Tailwind layout is in rem, so padding, buttons and inputs grow with it and long conditions reflow instead of running off the screen. Shared by the practice session, the variant page and the practicum (`ege_practice.html`, `ege_detail.html`, `quiz_detail.html`), each wrapping its own Alpine component in `<div class="present-root" x-data="presentMode()">`; the zoom lives in `localStorage` – one classroom, one projector. **The chrome itself is sized in px, not rem** (`.present-chrome` in `_present_mode.html`): the panel is built from Tailwind utilities, so at 200% its row of `h-9` buttons stood 72px tall – a line and a half of the lesson, on a wall where space is the scarce thing. Only the material scales; the panel stays the same size at every zoom. **Zoom is typed, not only clicked**: the percentage is an `<input type="number">` clamped by `setZoom` to 60–300% (60 because a big TV instead of a projector wants the text smaller, not larger), rounded to a whole percent so a typed 65 stays 65 while the buttons keep their 20% step. The field takes its value back from the state after the clamp, so it shows what was applied, not what was typed; an emptied field (`'' / 100` is 0, not NaN) is rejected and the previous zoom returns. **CSS `zoom` cannot be used here**: CodeMirror measures character width itself and under `zoom` mixes scaled rects with unscaled offsets – the code stays small and the caret drifts. For the same reason nothing may *ask* CodeMirror to re-measure after the scale changes: `refresh()`, `setOption` and recreating the instance all leave it silently unable to accept input (the click focuses its textarea, but the letters never reach the document). The only safe redraw is a document edit inside a user gesture, so the editor is blurred on a scale change (an unfocused CodeMirror draws no caret at all) and its geometry is fixed by the first click into it. All of it verified in a browser, variant by variant – do not "simplify" it back
- **Lesson show mode** (`static/js/article-present.js`) – the same projector, now on a textbook article, plus stepping through the lesson. **A slide is an existing `ArticleBlock`**, marked `data-slide` in `article_detail.html`: the lesson and its presentation are one text, so there is nothing for them to drift apart on – and a generated deck over 152 articles would have been a second copy to maintain. `articlePresent()` spreads `presentMode()` and adds the stepping; the slide nodes are kept in the closure, not in Alpine state, because a DOM node inside Alpine's Proxy stops comparing equal to itself (the same trap `present-mode.js` documents for `fullscreenElement`). Stepping is live **only in fullscreen** – outside it the page stays the article a student reads at home. Keys: `→ ↓ PageDown Space` forward, `← ↑ PageUp` back (a presentation clicker sends PageUp/PageDown, not arrows – without them the teacher is tied to the laptop), `Home/End`. A drop-down table of contents was built and removed: with the block titles on the slides themselves it answered nothing the counter and the arrows did not, and it cost a second row of chrome. **The article's font scale had to be given a rem twin**: `textbook-article.css` declares `--fs-h1 … --fs-table` in px, and the root-font-size trick moves nothing measured in px – the projector text would have stayed 18.5px at any zoom. The `.present-root:fullscreen .article-column` block redeclares those six variables in rem (same values ÷ 16); `ProjectorFontScaleTest` compares the two sets, so a seventh variable added to the scale and forgotten in the twin fails a test instead of a lesson. Widget captions stay in px on purpose – SVG coordinates live beside them and `zoom` would break their `getBoundingClientRect`

**Content block pattern**: Both `pages` and `lessons` use a reusable block model for flexible page composition with database-driven styling (fonts, colors, alignment, sizing).

**Async Code Execution System** (`quizzes` app):
- `consumers.py` – WebSocket consumer: `QuizConsumer` for code submissions
- `tasks.py` – Celery tasks for sandboxed Python code execution
- `routing.py` – WebSocket URL routing (`/ws/quiz/<quiz_id>/`)
- Frontend: `static/js/quiz-async.js` – WebSocket client with connection status tracking, UI updates without page reload

## Key Configuration

- Database credentials and Django secret key in `.env`
- PostgreSQL via psycopg2-binary
- Redis: localhost:6379 (broker for Celery and Django Channels)
- Celery: configured in `config/celery.py`, tasks in `quizzes/tasks.py`
- Channels: configured in `config/asgi.py`, routing in `quizzes/routing.py`
- Timezone: Asia/Novosibirsk
- **Tailwind CSS is precompiled**, not a CDN build: `static/css/tailwind.css` is generated from `static/css/tailwind.input.css` by `npm run tw:build` (config: `tailwind.config.js`, scans `templates/**/*.html` and `static/js/**/*.js`). A class that no template used before simply does not exist in the CSS until you rebuild – the browser silently ignores it and the layout looks unchanged. Always run `npm run tw:build` after adding new utility classes.
- Media files: `media/` (`lessons/{safe_title}/` for lesson files/presentations, `question_files/` for quiz files, `content/` for pages)
- Static assets: `static/js/` (quiz-async, ege-timer)
- Templates: `templates/` directory with subdirectories per app
- **JSON в шаблон – только через `quizzes.utils.js_json`, не `json.dumps`**:
  страницы вставляют данные в сырой `<script>` (`{{ items_json|safe }}`), а
  пишет эти данные ученик – свой ответ в `items_json`, свой код в
  `last_submissions_json`. `json.dumps` не экранирует `<` и `>`, поэтому строка
  `</script>` закрывала тег, и остаток становился разметкой на странице, которую
  учитель открывает под своей учётной записью. `js_json` – тот же `json.dumps`
  плюс таблица экранирования из `django.utils.html.json_script`.
- **Склонение по числу – фильтр `plural`, не `pluralize`** (`textbook/templatetags/textbook_tags.py`):
  `{{ n }} балл{{ n|plural:",а,ов" }}`. Встроенный Django-фильтр `pluralize` знает только две
  формы и на трёх (`",а,ов"`) молча возвращает пустую строку – отсюда были «2 балл» и
  «3 блок» на семи страницах. Три формы через запятую: для 1, для 2–4, для 5–20.
- **Типографика:** тире в проекте – только короткое en dash U+2013. Длинное em dash U+2014
  вычищено из шаблонов, seed-файлов учебника, пользовательских строк Python и БД – новое
  не добавлять. Проверка исходников: `rg -c $'—' templates textbook`.
  Проверка базы: `python manage.py fix_dashes --dry-run` (без флага – исправляет)
- **Шкала кегля – девять ступеней, других размеров в проекте нет.** Роль решает
  размер, а не страница: до шкалы один и тот же подзаголовок был 12px в отчёте о
  попытке, 14px на карточке задания и 18px на лендинге, а рядом жили девять
  произвольных значений между 9 и 17px (`text-[12.5px]`, `font-size: 13.5px`).

  | Роль | Класс | px |
  |---|---|---|
  | Ячейки таблиц, бейджи, счётчики, подписи под цифрой | `text-xs` | 12 |
  | Мета, формы, вспомогательный текст, плотный интерфейс | `text-sm` | 14 |
  | Основной текст, лид под заголовком страницы | `text-base` | 16 |
  | Лид лендинга, текст статьи учебника | `text-lg` | 18 |
  | Заголовок в компактной панели (шапка сессии, строка с аватаром), h3 | `text-xl` | 20 |
  | h2 | `text-2xl` | 24 |
  | **h1 страницы** | `text-2xl sm:text-3xl` | 24 → 30 |
  | **h1 лендинга** (главные учебника, спецкурса, ЕГЭ, уроков, «Обо мне») | `text-4xl sm:text-5xl` | 36 → 48 |

  Крупнее 48px – только display-цифры (балл прогноза, номера заданий на карте,
  игровое поле «Своей игры»), это графика, а не текст. Статья учебника ходит через
  ту же шкалу, но своими переменными: `--fs-h1: 30px … --fs-cap: 14px` в
  `static/css/textbook-article.css` (плюс rem-двойник для проектора – см.
  `ProjectorFontScaleTest`). Исключения из шкалы – четыре файла, где буквы работают
  как графика; они перечислены в `textbook.tests.FontScaleTest.EXCEPTIONS`.
  **Произвольный `text-[Npx]` и `font-size` мимо ступени роняют `FontScaleTest`** –
  ступень выбирается ближайшая, полпикселя «чтобы влезло» не добавляем.

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
- **Gunicorn:** `site.service` (socket: `/run/gunicorn/site.sock`) – HTTP requests
- **Daphne:** `daphne.service` (socket: `/run/daphne/site.sock`) – WebSocket requests
- **Celery:** `celery.service` – async task worker for code execution
- **Celery Beat:** `celerybeat.service` – periodic task scheduler (stale task cleanup, etc.)
- **Redis:** `redis-server.service` – message broker for Celery and Channels
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

- 🎨 **designer** – UI/UX, Tailwind, Playwright скриншоты
- 🔍 **reviewer** – безопасность, GitHub, код-ревью
- 📚 **content** – Quiz генерация, идеи развития
- 🔧 **devops** – диагностика (**READ-ONLY!**)

### Quiz Import (`load_quiz`)

Management command for importing quizzes from JSON files. Uses a custom format (not Django fixtures) – no `pk` required, Django assigns IDs automatically. All objects are created in a single transaction.

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
