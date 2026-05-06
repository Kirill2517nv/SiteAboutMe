from django.db import models
from django.contrib.auth.models import User


STATUS_CHOICES = [
    ('pending', 'На проверке'),
    ('approved', 'Одобрена'),
    ('rejected', 'Отклонена'),
]

MEDIA_TYPE_CHOICES = [
    ('image', 'Изображение'),
    ('audio', 'Аудио'),
    ('video', 'Видео'),
]


def question_media_upload_path(instance, filename):
    return f'games/svoya-igra/uploads/{filename}'


class Category(models.Model):
    title = models.CharField(max_length=200, verbose_name='Название темы')
    description = models.TextField(blank=True, verbose_name='Описание')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_si_categories', verbose_name='Автор'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус'
    )
    moderator_comment = models.TextField(blank=True, verbose_name='Комментарий модератора')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Тема'
        verbose_name_plural = 'Темы'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_by', 'status']),
        ]

    def __str__(self):
        return self.title


class Question(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE,
        related_name='questions', verbose_name='Тема'
    )
    text = models.TextField(verbose_name='Текст вопроса')
    answer = models.TextField(verbose_name='Ответ')
    points = models.IntegerField(default=100, verbose_name='Стоимость')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.category.title} — {self.points} очков'


class QuestionMedia(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE,
        related_name='media_files', verbose_name='Вопрос'
    )
    media_type = models.CharField(
        max_length=10, choices=MEDIA_TYPE_CHOICES, verbose_name='Тип медиа'
    )
    file = models.FileField(
        upload_to=question_media_upload_path, verbose_name='Файл'
    )
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    is_answer = models.BooleanField(default=False, verbose_name='Медиа к ответу')

    class Meta:
        verbose_name = 'Медиафайл вопроса'
        verbose_name_plural = 'Медиафайлы вопросов'
        ordering = ['is_answer', 'media_type', 'order']

    def __str__(self):
        prefix = 'Ответ' if self.is_answer else 'Вопрос'
        return f'{prefix} — {self.get_media_type_display()} #{self.question_id}'


class GamePack(models.Model):
    title = models.CharField(max_length=200, verbose_name='Название пакета')
    description = models.TextField(blank=True, verbose_name='Описание')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_si_packs', verbose_name='Автор'
    )
    is_public = models.BooleanField(default=False, verbose_name='Публичный')
    categories = models.ManyToManyField(
        Category, through='GamePackCategory', verbose_name='Темы'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Игровой пакет'
        verbose_name_plural = 'Игровые пакеты'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class GamePackCategory(models.Model):
    game_pack = models.ForeignKey(
        GamePack, on_delete=models.CASCADE,
        related_name='pack_categories', verbose_name='Пакет'
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE,
        related_name='in_packs', verbose_name='Тема'
    )
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Тема в пакете'
        verbose_name_plural = 'Темы в пакете'
        ordering = ['order']
        unique_together = [('game_pack', 'category')]

    def __str__(self):
        return f'{self.game_pack.title} / {self.category.title}'


class GameSession(models.Model):
    game_pack = models.ForeignKey(
        GamePack, on_delete=models.CASCADE,
        related_name='sessions', verbose_name='Пакет'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='si_sessions', verbose_name='Игрок'
    )
    board_state = models.JSONField(default=dict, verbose_name='Состояние доски')
    players = models.JSONField(default=list, verbose_name='Игроки')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Начата')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Игровая сессия'
        verbose_name_plural = 'Игровые сессии'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', 'is_active']),
            models.Index(fields=['game_pack', 'is_active']),
        ]

    def __str__(self):
        return f'Сессия #{self.id} — {self.game_pack.title}'
