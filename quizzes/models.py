from django.db import models
from django.conf import settings

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

class Question(models.Model):
    TYPE_CHOICES = [
        ('choice', 'Выбор ответа'),
        ('text', 'Свободный ответ'),
        ('code', 'Написание кода (Python)'),
    ]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions', verbose_name="Тест")
    text = models.TextField(verbose_name="Текст вопроса")
    question_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='choice', verbose_name="Тип вопроса")
    
    data_file = models.FileField(upload_to='question_files/', blank=True, null=True, verbose_name="Файл с данными (для скачивания)")
    correct_text_answer = models.CharField(max_length=200, blank=True, null=True, verbose_name="Правильный ответ (текст)")
    
    class Meta:
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"

    def __str__(self):
        return self.text[:50] + "..." if len(self.text) > 50 else self.text

    def get_title(self):
        """Возвращает первую строку текста (заголовок)"""
        return self.text.strip().split('\n')[0]

    def get_body(self):
        """Возвращает все остальные строки (тело вопроса)"""
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

class UserAnswer(models.Model):
    user_result = models.ForeignKey(UserResult, on_delete=models.CASCADE, related_name='answers', verbose_name="Результат попытки")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name="Вопрос")
    
    selected_choice = models.ForeignKey(Choice, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Выбранный вариант")
    text_answer = models.CharField(max_length=200, null=True, blank=True, verbose_name="Текстовый ответ")
    code_answer = models.TextField(null=True, blank=True, verbose_name="Код ученика")
    error_log = models.TextField(null=True, blank=True, verbose_name="Лог ошибки")
    
    is_correct = models.BooleanField(default=False, verbose_name="Верно?")

    class Meta:
        verbose_name = "Ответ пользователя"
        verbose_name_plural = "Ответы пользователя"
        indexes = [
            models.Index(fields=['user_result', 'is_correct']),  # Для поиска правильных ответов
            models.Index(fields=['question', 'is_correct']),  # Для статистики по вопросам
        ]