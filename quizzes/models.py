from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.models import StudentGroup

User = get_user_model()


def normalize_text_answer(answer: str) -> str:
    """Нормализация текстового ответа: strip, lowercase, удаление ведущих нулей."""
    answer = answer.lower().strip()
    while answer.startswith("0") and len(answer) > 1:
        answer = answer[1:]

    return answer


class Quiz(models.Model):
    # 'bank' – контейнер тематической подборки задач ЕГЭ, импортированной с kompege.
    # Целиком такой квиз никто не решает: из него сессии тренировки берут задачи по
    # ege_number. В списке вариантов не появляется – там фильтр quiz_type='exam'.
    QUIZ_TYPE_CHOICES = [('standard', 'Стандартный'), ('exam', 'ЕГЭ'), ('bank', 'Банк задач ЕГЭ')]
    EXAM_MODE_CHOICES = [('exam', 'Экзамен'), ('practice', 'Тренировка')]

    title = models.CharField(max_length=200, verbose_name="Название теста")
    description = models.TextField(verbose_name="Описание", blank=True)
    max_attempts = models.PositiveIntegerField(default=3, verbose_name="Максимум попыток", help_text="Сколько раз ученик может пройти тест. 0 - безлимитно.")

    quiz_type = models.CharField(max_length=10, choices=QUIZ_TYPE_CHOICES, default='standard', verbose_name="Тип теста")
    exam_mode = models.CharField(max_length=10, choices=EXAM_MODE_CHOICES, default='practice', blank=True, verbose_name="Режим ЕГЭ")
    is_public = models.BooleanField(default=False, verbose_name="Публичный доступ", help_text="Доступен всем без назначения")
    is_self_check = models.BooleanField(default=False, verbose_name="Самопроверка учебника", help_text="Тест-самопроверка статьи учебника: доступен любому авторизованному ученику через статью, скрыт из общего списка тестов")
    slug = models.SlugField(max_length=100, blank=True, null=True, unique=True,
                            verbose_name="Slug (для медиа-путей)")

    start_date = models.DateTimeField(null=True, blank=True, verbose_name="Начало доступа", help_text="Дата и время, с которого тест становится доступным")
    end_date = models.DateTimeField(null=True, blank=True, verbose_name="Конец доступа", help_text="Дата и время, после которого тест закрывается")

    class Meta:
        verbose_name = "Тест"
        verbose_name_plural = "Тесты"

    def __str__(self):
        return self.title

class QuizAssignment(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='assignments', verbose_name="Тест")
    group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Группа", related_name='quiz_assignments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Ученик", related_name='quiz_assignments')
    
    start_date = models.DateTimeField(null=True, blank=True, verbose_name="Начало доступа", help_text="Переопределяет глобальную дату начала")
    end_date = models.DateTimeField(null=True, blank=True, verbose_name="Конец доступа", help_text="Переопределяет глобальную дату конца")
    max_attempts = models.PositiveIntegerField(null=True, blank=True, verbose_name="Максимум попыток", help_text="Переопределяет глобальное кол-во попыток")

    class Meta:
        verbose_name = "Назначение теста"
        verbose_name_plural = "Назначения тестов"
        # Ensure either group or user is set (can be enforced in clean() or just logically)
        # Also maybe unique constraints (one assignment per user per quiz? or precedence?)

    def __str__(self):
        if self.user:
            return f"{self.quiz} -> {self.user}"
        return f"{self.quiz} -> {self.group}"

class Question(models.Model):
    TYPE_CHOICES = [
        ('choice', 'Выбор ответа'),
        ('text', 'Свободный ответ'),
        ('code', 'Написание кода (Python)'),
    ]

    DIFFICULTY_CHOICES = [(1, 'Базовая'), (2, 'Повышенная'), (3, 'Высокая')]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions', verbose_name="Тест")
    title = models.CharField(max_length=200, verbose_name="Заголовок вопроса", blank=True, help_text="Используется для отображения и сортировки. Если пусто – берётся первая строка текста.")
    text = models.TextField(verbose_name="Текст вопроса")
    question_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='choice', verbose_name="Тип вопроса")
    
    correct_text_answer = models.CharField(max_length=200, blank=True, null=True, verbose_name="Правильный ответ (текст)")

    ege_number = models.PositiveIntegerField(null=True, blank=True, verbose_name="Номер задачи ЕГЭ")
    topic = models.CharField(max_length=200, blank=True, default='', verbose_name="Тема")
    points = models.PositiveIntegerField(default=1, verbose_name="Баллы")
    difficulty = models.PositiveSmallIntegerField(
        choices=DIFFICULTY_CHOICES, default=1, verbose_name="Сложность",
        help_text="Стартовое значение из импорта. Фактическую сложность считает "
                  "recalc_ege_difficulty по доле верных первых попыток."
    )
    solve_rate = models.FloatField(
        null=True, blank=True, verbose_name="Доля верных первых попыток",
        help_text="Пересчитывается автоматически, когда наберётся достаточно попыток. "
                  "Пусто – данных мало, сложность берётся из поля выше."
    )
    external_id = models.CharField(
        max_length=64, blank=True, default='', db_index=True, verbose_name="ID на источнике",
        help_text="ID задачи на kompege.ru. По нему load_ege обновляет задачу вместо "
                  "создания дубля при повторном импорте подборки."
    )
    source_url = models.URLField(blank=True, default='', verbose_name="Ссылка на оригинал")
    group_id = models.CharField(
        max_length=64, blank=True, default='', db_index=True, verbose_name="Связка задач",
        help_text="Задачи с одинаковым значением выдаются только вместе и в одном "
                  "порядке. Так устроены задания 19–21: условие игры описано "
                  "в 19-м, а 20-е и 21-е на него ссылаются. Пусто – задача сама по себе."
    )
    group_order = models.PositiveSmallIntegerField(
        default=0, verbose_name="Место в связке",
        help_text="Порядок внутри связки: 0 – первая задача, за ней 1, 2. "
                  "Без связки не используется."
    )
    classroom_only = models.BooleanField(
        default=False, db_index=True, verbose_name="Только для работы в классе",
        help_text="Задача выдаётся лишь по кнопке «Задачи для урока» и одна и та же "
                  "у всех учеников. В обычные тренировки и в экзамен не попадает."
    )
    exam_only = models.BooleanField(
        default=False, db_index=True, verbose_name="Только для экзамена",
        help_text="Задача не попадает в учебные тренировки. Резерв нужен, чтобы "
                  "режим «Экзамен» проверял знание темы, а не память о задачах, "
                  "которые ученик уже прорешал на тренировках."
    )
    alternative_answers = models.JSONField(null=True, blank=True, verbose_name="Альтернативные ответы", help_text='Список строк, например: ["42", "42.0"]')
    hint = models.TextField(
        blank=True, default='', verbose_name="Подсказка",
        help_text="Markdown. Ученик не видит ни текста, ни самого факта наличия "
                  "подсказки, пока она не откроется: три неудачные попытки, "
                  "меньше трёх дней до дедлайна блока или рубильник в блоке."
    )

    # Пороги доли верных первых попыток, отделяющие уровни сложности друг от друга.
    # Держатся здесь, потому что те же числа нужны SQL-выражению в ege_practice.py:
    # разъехавшись, они дали бы фильтр «повышенная», выдающий базовые задачи.
    SOLVE_RATE_EASY = 0.7
    SOLVE_RATE_MEDIUM = 0.4

    class Meta:
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"
        indexes = [
            # Основной запрос отбора задач для сессии тренировки.
            models.Index(fields=['ege_number', 'difficulty']),
        ]

    def __str__(self):
        title = self.get_title()
        return title[:50] + "..." if len(title) > 50 else title

    def effective_difficulty(self):
        """
        Сложность с поправкой на факт: пока попыток мало, верим разметке импорта,
        дальше – доле учеников, решивших задачу с первого раза.
        """
        if self.solve_rate is None:
            return self.difficulty
        if self.solve_rate >= self.SOLVE_RATE_EASY:
            return 1
        if self.solve_rate >= self.SOLVE_RATE_MEDIUM:
            return 2
        return 3

    def get_effective_difficulty_display(self):
        return dict(self.DIFFICULTY_CHOICES)[self.effective_difficulty()]

    def get_title(self):
        """Возвращает заголовок: поле title или первую строку текста"""
        if self.title:
            return self.title
        return self.text.strip().split('\n')[0]

    def check_text_answer(self, user_answer: str) -> bool:
        """Проверяет текстовый ответ с учётом нормализации и альтернативных ответов."""
        normalized = normalize_text_answer(user_answer)
        if normalize_text_answer(self.correct_text_answer or '') == normalized:
            return True
        if self.alternative_answers:
            return any(normalize_text_answer(alt) == normalized for alt in self.alternative_answers)
        return False

    def get_body(self):
        """
        Возвращает тело вопроса:
        - Если title заполнен → весь text (первая строка - это условие, не заголовок)
        - Если title пустой → text без первой строки (первая строка используется как заголовок)
        """
        if self.title:
            # Заголовок есть отдельно, возвращаем весь текст
            return self.text.strip()

        # Заголовок не задан, используем первую строку как заголовок
        lines = self.text.strip().split('\n')
        if len(lines) > 1:
            return '\n'.join(lines[1:])
        return ""

def _ege_slug(quiz):
    """Возвращает slug квиза если он EGE, иначе None."""
    if quiz and quiz.quiz_type == 'exam' and quiz.slug:
        return quiz.slug
    return None


def question_image_upload_path(instance, filename):
    slug = _ege_slug(instance.question.quiz)
    if slug:
        return f'ege/{slug}/images/{filename}'
    return f'question_images/{filename}'


def question_file_upload_path(instance, filename):
    slug = _ege_slug(instance.question.quiz)
    if slug:
        return f'ege/{slug}/files/{filename}'
    return f'question_files/{filename}'


def solution_file_upload_path(instance, filename):
    slug = _ege_slug(instance.quiz)
    if slug:
        return f'ege/{slug}/solutions/u{instance.user_id}/{filename}'
    return f'solutions/{filename}'


def solution_image_upload_path(instance, filename):
    slug = _ege_slug(instance.quiz)
    if slug:
        return f'ege/{slug}/solutions/u{instance.user_id}/images/{filename}'
    return f'solutions/images/{filename}'


class QuestionImage(models.Model):
    """Изображение, отображаемое inline под текстом вопроса."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='images', verbose_name="Вопрос")
    image = models.ImageField(upload_to=question_image_upload_path, verbose_name="Изображение")
    alt_text = models.CharField(max_length=200, blank=True, verbose_name="Альтернативный текст")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Изображение вопроса"
        verbose_name_plural = "Изображения вопросов"
        ordering = ['order', 'id']

    def __str__(self):
        return f"Изображение для {self.question} (#{self.order})"


class QuestionFile(models.Model):
    """Файл для скачивания, прикреплённый к вопросу."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='files', verbose_name="Вопрос")
    file = models.FileField(upload_to=question_file_upload_path, verbose_name="Файл")
    description = models.CharField(max_length=200, blank=True, verbose_name="Описание файла")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Файл вопроса"
        verbose_name_plural = "Файлы вопросов"
        ordering = ['order', 'id']

    def __str__(self):
        return f"Файл для {self.question}: {self.get_filename()}"

    def get_filename(self):
        import os
        return os.path.basename(self.file.name)


class TestCase(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='test_cases', verbose_name="Вопрос")
    input_data = models.TextField(verbose_name="Входные данные (Stdin)", blank=True, help_text="То, что будет подано на вход программе")
    output_data = models.TextField(verbose_name="Ожидаемый вывод (Stdout)", help_text="То, что программа должна вывести")

    class Meta:
        verbose_name = "Тестовый пример"
        verbose_name_plural = "Тестовые примеры"

    def __str__(self):
        return f"Test for {self.question}"

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices', verbose_name="Вопрос")
    text = models.CharField(max_length=200, verbose_name="Текст ответа")
    is_correct = models.BooleanField(default=False, verbose_name="Правильный ответ")
    
    class Meta:
        # Порядок вариантов = порядок создания. Без явной сортировки Postgres
        # отдаёт строки в физическом порядке, а он после пересоздания вопросов
        # сидами меняется — ученик видел бы варианты каждый раз по-новому.
        ordering = ['id']
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответа"

    def __str__(self):
        return self.text

class UserResult(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Пользователь")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, verbose_name="Тест")
    score = models.IntegerField(verbose_name="Баллы")
    date_completed = models.DateTimeField(auto_now_add=True, verbose_name="Дата прохождения")
    duration = models.DurationField(null=True, blank=True, verbose_name="Время прохождения")
    
    class Meta:
        verbose_name = "Результат пользователя"
        verbose_name_plural = "Результаты пользователей"
        indexes = [
            models.Index(fields=['user', 'quiz']),  # Для фильтрации по пользователю и квизу
            models.Index(fields=['quiz', 'date_completed']),  # Для сортировки результатов по квизу
        ]

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title}: {self.score}"

class CodeSubmission(models.Model):
    """
    Модель для отслеживания асинхронной проверки кода.
    Каждая отправка кода создает запись, которая обновляется по мере выполнения.
    """
    STATUS_CHOICES = [
        ('pending', 'В очереди'),
        ('running', 'Выполняется'),
        ('success', 'Успешно'),
        ('failed', 'Ошибка'),
        ('error', 'Системная ошибка'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='code_submissions', verbose_name="Пользователь")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='submissions', verbose_name="Вопрос")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='submissions', verbose_name="Тест")
    code = models.TextField(verbose_name="Код")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    is_correct = models.BooleanField(null=True, verbose_name="Правильно?")
    score = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Балл",
        help_text="Заполняется только там, где балл частичный (задания 26 и 27). Пусто – задача оценивается «верно/неверно».",
    )
    error_log = models.TextField(null=True, blank=True, verbose_name="Лог ошибки")
    celery_task_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID задачи Celery")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершено")

    cpu_time_ms = models.FloatField(null=True, blank=True, verbose_name="CPU-время (мс)")
    memory_kb = models.IntegerField(null=True, blank=True, verbose_name="Пиковая память (КБ)")

    class Meta:
        verbose_name = "Отправка кода"
        verbose_name_plural = "Отправки кода"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'quiz', 'question']),
            models.Index(fields=['status']),
            models.Index(fields=['celery_task_id']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.question} ({self.status})"


class ExamTaskProgress(models.Model):
    """Прогресс пользователя по конкретной задаче ЕГЭ (время, попытки, статус)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_progress', verbose_name="Пользователь")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='task_progress', verbose_name="Вариант")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='exam_progress', verbose_name="Задача")
    time_spent_seconds = models.PositiveIntegerField(default=0, verbose_name="Время (секунды)")
    attempts_to_solve = models.PositiveIntegerField(default=0, verbose_name="Количество попыток")
    is_solved = models.BooleanField(default=False, verbose_name="Решена")
    score = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Балл",
        help_text="Заполняется только там, где балл частичный (задания 26 и 27). Пусто – задача оценивается «верно/неверно».",
    )

    first_solved_at = models.DateTimeField(null=True, blank=True, verbose_name="Время первого решения")
    best_cpu_time_ms = models.FloatField(null=True, blank=True, verbose_name="Лучшее время CPU (мс)")
    best_cpu_code = models.TextField(blank=True, default='', verbose_name="Код лучшей попытки по CPU")
    best_memory_kb = models.IntegerField(null=True, blank=True, verbose_name="Лучшая память (КБ)")
    best_memory_code = models.TextField(blank=True, default='', verbose_name="Код лучшей попытки по памяти")

    class Meta:
        verbose_name = "Прогресс задачи ЕГЭ"
        verbose_name_plural = "Прогресс задач ЕГЭ"
        unique_together = ['user', 'quiz', 'question']
        indexes = [
            models.Index(fields=['user', 'quiz']),
            models.Index(fields=['is_solved']),
        ]

    def __str__(self):
        status = "решена" if self.is_solved else f"{self.attempts_to_solve} попыток"
        return f"{self.user.username} – задача {self.question_id} ({status})"


class PracticeSession(models.Model):
    """
    Сессия тренировки: короткая пачка задач, отобранная под конкретную цель.

    Одна модель закрывает три сценария, которые отличаются только правилом отбора:
    практикум после статьи теории, свободная тренировка по теме и работа над
    ошибками. Плодить под каждый отдельную сущность нечего – различие живёт
    в поле kind и в ege_practice.pick_questions().
    """

    KIND_CHOICES = [
        ('topic', 'По теме'),
        ('mistakes', 'Работа над ошибками'),
        ('mixed', 'Смешанная'),
        # Один и тот же набор задач у всех учеников: на уроке «задача 1»
        # обязана быть одной задачей для всего класса.
        ('classroom', 'Работа в классе'),
        # Задача уже решена, ученик переписывает код ради времени и памяти.
        # Такая сессия не оценивается: она про качество решения, а не про знание.
        ('retry', 'Переписать решение'),
    ]
    # study – проверка сразу после каждой задачи, можно ответить ещё раз,
    # exam – ответы сохраняются молча, разбор в конце сессии.
    # Значение в базе остаётся 'study': переименование чисто словесное, ученику
    # везде говорим «тренировка», а не «учёба».
    MODE_CHOICES = [('study', 'Тренировка'), ('exam', 'Экзамен')]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='practice_sessions', verbose_name="Ученик")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='topic', verbose_name="Тип сессии")
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='study', verbose_name="Режим")
    ege_number = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Номер задания ЕГЭ",
        help_text="Пусто для работы над ошибками и смешанной сессии – там задачи разных заданий."
    )
    difficulty = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=Question.DIFFICULTY_CHOICES,
        verbose_name="Сложность", help_text="Пусто – любая."
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Начата")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершена")

    class Meta:
        verbose_name = "Сессия тренировки ЕГЭ"
        verbose_name_plural = "Сессии тренировки ЕГЭ"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        target = f"задание {self.ege_number}" if self.ege_number else self.get_kind_display()
        return f"{self.user.username} – {target} ({self.created_at:%d.%m.%Y})"

    @property
    def is_finished(self):
        return self.finished_at is not None

    @property
    def deadline(self):
        """
        Момент, когда экзамен закрывается сам. У тренировки лимита нет.

        Состав экзамена подбирается так, чтобы уместиться в час по нормативу
        ЕГЭ, – без жёсткого конца это была бы та же тренировка, только без
        подсказок. Отсчёт идёт от created_at, а не от первого ответа: часы
        на реальном экзамене тоже не ждут, пока ученик соберётся.
        """
        from .ege_constants import EXAM_MINUTES

        if self.mode != 'exam':
            return None
        return self.created_at + timedelta(minutes=EXAM_MINUTES)

    @property
    def is_expired(self):
        """Время экзамена вышло, а сессия всё ещё открыта."""
        deadline = self.deadline
        return bool(deadline and not self.finished_at and timezone.now() >= deadline)


class PracticeItem(models.Model):
    """
    Одна задача внутри сессии – и одновременно единственный журнал попыток тренировки.

    Из него считается вся аналитика: точность по заданию, среднее время, динамика
    по неделям, пул задач для работы над ошибками. ExamTaskProgress для этого не
    годится – он хранит агрегат («решена / столько-то попыток») без истории, а
    работа над ошибками должна знать, чем закончилась именно последняя попытка.
    """

    session = models.ForeignKey(PracticeSession, on_delete=models.CASCADE, related_name='items', verbose_name="Сессия")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='practice_items', verbose_name="Задача")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Порядок в сессии")

    text_answer = models.CharField(max_length=200, blank=True, default='', verbose_name="Ответ ученика")
    submission = models.ForeignKey(
        CodeSubmission, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='practice_items', verbose_name="Отправка кода"
    )
    is_correct = models.BooleanField(null=True, verbose_name="Верно?", help_text="Пусто – ученик ещё не отвечал.")
    score = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Балл",
        help_text="Заполняется только там, где балл частичный (задания 26 и 27). Пусто – задача оценивается «верно/неверно».",
    )

    attempts = models.PositiveSmallIntegerField(
        default=0, verbose_name="Попыток",
        help_text="Сколько раз ученик нажал «Проверить». При is_correct=True – с какой попытки решил."
    )
    gave_up = models.BooleanField(
        default=False, verbose_name="Открыл ответ",
        help_text="Ученик посмотрел верный ответ, не решив задачу. Считается как нерешённая."
    )
    carried = models.BooleanField(
        default=False, db_index=True, verbose_name="Ответ перенесён",
        help_text="Задача попала в сессию только как часть связки (19–21): ученик "
                  "решил её раньше, ответ подставлен, решать заново нечего. "
                  "В статистику и в работу над ошибками такая запись не идёт."
    )
    seconds = models.PositiveIntegerField(default=0, verbose_name="Время на задачу (секунды)")
    answered_at = models.DateTimeField(null=True, blank=True, verbose_name="Момент ответа")

    class Meta:
        verbose_name = "Задача сессии"
        verbose_name_plural = "Задачи сессий"
        ordering = ['order']
        unique_together = ['session', 'question']
        indexes = [
            models.Index(fields=['session', 'order']),
            # Пул ошибок и точность по заданию: ищем по задаче и исходу.
            models.Index(fields=['question', 'is_correct']),
            models.Index(fields=['answered_at']),
        ]

    @property
    def is_locked(self):
        """
        Задача закрыта: либо решена, либо ученик открыл ответ.

        Без замка тренировка не измеряет ничего: неверный ответ показывал
        правильный, ученик вписывал его и получал зачёт. Теперь верный ответ
        отдаётся только по кнопке «Показать ответ», и это фиксируется.

        В сессии «Переписать решение» замка нет вовсе: там весь смысл в том,
        чтобы отправлять вариант за вариантом и смотреть на время и память.
        """
        if self.session.kind == 'retry':
            return False
        return bool(self.is_correct) or self.gave_up

    def __str__(self):
        if self.is_correct is None:
            status = "без ответа"
        elif self.gave_up:
            status = "открыл ответ"
        elif self.is_correct:
            status = f"верно с попытки {self.attempts}" if self.attempts > 1 else "верно"
        else:
            status = "неверно"
        return f"Сессия {self.session_id}, задача {self.question_id} ({status})"


class SolutionAttachment(models.Model):
    """Дополнительные материалы к решению задачи (файл, комментарий, изображение)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='solution_attachments', verbose_name="Пользователь")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='solution_attachments', verbose_name="Вариант")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='solution_attachments', verbose_name="Задача")
    file = models.FileField(upload_to=solution_file_upload_path, blank=True, null=True, verbose_name="Файл")
    comment = models.TextField(blank=True, default='', verbose_name="Комментарий")
    image = models.ImageField(upload_to=solution_image_upload_path, blank=True, null=True, verbose_name="Изображение")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Доп. материал к решению"
        verbose_name_plural = "Доп. материалы к решениям"
        unique_together = ['user', 'quiz', 'question']

    def __str__(self):
        return f"Материал: {self.user.username} – задача {self.question_id}"

    def get_filename(self):
        import os
        return os.path.basename(self.file.name) if self.file else ''


class UserAnswer(models.Model):
    user_result = models.ForeignKey(UserResult, on_delete=models.CASCADE, related_name='answers', verbose_name="Результат попытки")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name="Вопрос")

    selected_choice = models.ForeignKey(Choice, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Выбранный вариант")
    text_answer = models.CharField(max_length=200, null=True, blank=True, verbose_name="Текстовый ответ")
    code_answer = models.TextField(null=True, blank=True, verbose_name="Код ученика")
    error_log = models.TextField(null=True, blank=True, verbose_name="Лог ошибки")

    is_correct = models.BooleanField(default=False, verbose_name="Верно?")
    score = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Балл",
        help_text="Заполняется только там, где балл частичный (задания 26 и 27). Пусто – задача оценивается «верно/неверно».",
    )
    submission = models.ForeignKey(CodeSubmission, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Отправка кода")

    class Meta:
        verbose_name = "Ответ пользователя"
        verbose_name_plural = "Ответы пользователя"
        indexes = [
            models.Index(fields=['user_result', 'is_correct']),
            models.Index(fields=['question', 'is_correct']),
        ]


class SolutionLike(models.Model):
    """Лайк решения другого пользователя."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='solution_likes', verbose_name="Пользователь")
    answer = models.ForeignKey(UserAnswer, on_delete=models.CASCADE, related_name='likes', verbose_name="Ответ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата")

    class Meta:
        verbose_name = "Лайк решения"
        verbose_name_plural = "Лайки решений"
        constraints = [
            models.UniqueConstraint(fields=['user', 'answer'], name='unique_solution_like'),
        ]

    def __str__(self):
        return f"{self.user.username} -> answer #{self.answer_id}"


class HintChoice(models.Model):
    """Что ученик выбрал, когда ему предложили подсказку: взял или отказался.

    Ученику эта запись нигде не показывается и на баллы не влияет — она нужна
    учителю в статистике теста.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hint_choices', verbose_name="Ученик")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='hint_choices', verbose_name="Задача")
    accepted = models.BooleanField(default=False, verbose_name="Взял подсказку")
    offered_at = models.DateTimeField(auto_now_add=True, verbose_name="Предложена")
    decided_at = models.DateTimeField(auto_now=True, verbose_name="Последний выбор")

    class Meta:
        verbose_name = "Выбор по подсказке"
        verbose_name_plural = "Выборы по подсказкам"
        constraints = [
            models.UniqueConstraint(fields=['user', 'question'], name='unique_hint_choice'),
        ]

    def __str__(self):
        verdict = "взял" if self.accepted else "отказался"
        return f"{self.user.username} – задача {self.question_id}: {verdict}"
