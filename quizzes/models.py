from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MaxLengthValidator
from accounts.models import StudentGroup

User = get_user_model()

class Quiz(models.Model):
    title = models.CharField(max_length=200, verbose_name="Название теста")
    description = models.TextField(verbose_name="Описание", blank=True)
    max_attempts = models.PositiveIntegerField(default=3, verbose_name="Максимум попыток", help_text="Сколько раз ученик может пройти тест. 0 - безлимитно.")
    
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

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions', verbose_name="Тест")
    title = models.CharField(max_length=200, verbose_name="Заголовок вопроса", blank=True, help_text="Используется для отображения и сортировки. Если пусто — берётся первая строка текста.")
    text = models.TextField(verbose_name="Текст вопроса")
    question_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='choice', verbose_name="Тип вопроса")
    
    data_file = models.FileField(upload_to='question_files/', blank=True, null=True, verbose_name="Файл с данными (для скачивания)")
    correct_text_answer = models.CharField(max_length=200, blank=True, null=True, verbose_name="Правильный ответ (текст)")
    
    class Meta:
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"

    def __str__(self):
        title = self.get_title()
        return title[:50] + "..." if len(title) > 50 else title

    def get_title(self):
        """Возвращает заголовок: поле title или первую строку текста"""
        if self.title:
            return self.title
        return self.text.strip().split('\n')[0]

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
    error_log = models.TextField(null=True, blank=True, verbose_name="Лог ошибки")
    celery_task_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID задачи Celery")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершено")

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


class HelpRequest(models.Model):
    """Запрос помощи от ученика по конкретному code-вопросу (один тред на ученика × вопрос)."""
    STATUS_CHOICES = [
        ('open', 'Открыт'),
        ('answered', 'Отвечен'),
        ('resolved', 'Решён'),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='help_requests', verbose_name="Ученик")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='help_requests', verbose_name="Вопрос")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='help_requests', verbose_name="Тест")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")
    has_unread_for_teacher = models.BooleanField(default=True, verbose_name="Непрочитано учителем")
    has_unread_for_student = models.BooleanField(default=False, verbose_name="Непрочитано учеником")

    class Meta:
        verbose_name = "Запрос помощи"
        verbose_name_plural = "Запросы помощи"
        unique_together = ['student', 'question']
        indexes = [
            models.Index(fields=['status', 'has_unread_for_teacher']),
        ]

    def __str__(self):
        return f"Помощь: {self.student.username} → {self.question} ({self.get_status_display()})"


class HelpComment(models.Model):
    """Сообщение в треде запроса помощи."""
    help_request = models.ForeignKey(HelpRequest, on_delete=models.CASCADE, related_name='comments', verbose_name="Запрос помощи")
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Автор")
    text = models.TextField(
        verbose_name="Текст комментария",
        validators=[MaxLengthValidator(10000, message="Комментарий не может превышать 10000 символов")]
    )
    line_number = models.PositiveIntegerField(null=True, blank=True, verbose_name="Номер строки")
    code_snapshot = models.TextField(null=True, blank=True, verbose_name="Снапшот кода")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")

    class Meta:
        verbose_name = "Комментарий помощи"
        verbose_name_plural = "Комментарии помощи"
        ordering = ['created_at']

    def __str__(self):
        line_info = f" (строка {self.line_number})" if self.line_number else ""
        return f"{self.author.username}{line_info}: {self.text[:50]}"


class UserAnswer(models.Model):
    user_result = models.ForeignKey(UserResult, on_delete=models.CASCADE, related_name='answers', verbose_name="Результат попытки")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name="Вопрос")

    selected_choice = models.ForeignKey(Choice, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Выбранный вариант")
    text_answer = models.CharField(max_length=200, null=True, blank=True, verbose_name="Текстовый ответ")
    code_answer = models.TextField(null=True, blank=True, verbose_name="Код ученика")
    error_log = models.TextField(null=True, blank=True, verbose_name="Лог ошибки")

    is_correct = models.BooleanField(default=False, verbose_name="Верно?")
    submission = models.ForeignKey(CodeSubmission, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Отправка кода")

    class Meta:
        verbose_name = "Ответ пользователя"
        verbose_name_plural = "Ответы пользователя"
        indexes = [
            models.Index(fields=['user_result', 'is_correct']),  # Для поиска правильных ответов
            models.Index(fields=['question', 'is_correct']),  # Для статистики по вопросам
        ]
