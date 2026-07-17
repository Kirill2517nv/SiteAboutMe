from django.conf import settings
from django.db import models
from django.urls import reverse


def article_image_upload(instance, filename):
    """Путь загрузки картинок блоков: textbook/articles/{slug}/{filename}."""
    slug = instance.article.slug or f'article_{instance.article_id}'
    return f'textbook/articles/{slug}/{filename}'


class Section(models.Model):
    """Тематический блок учебного материала (21 блок плана)."""

    title = models.CharField(max_length=200, verbose_name="Название блока")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="URL-идентификатор")
    description = models.TextField(blank=True, verbose_name="Краткое описание")
    thumbnail = models.ImageField(
        upload_to='textbook/sections/', blank=True, null=True,
        verbose_name="Превью изображение"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_published = models.BooleanField(default=False, verbose_name="Опубликовано")

    class Meta:
        ordering = ['order', 'title']
        verbose_name = "Блок учебника"
        verbose_name_plural = "Блоки учебника"

    def __str__(self):
        return self.title


class EgeTask(models.Model):
    """Справочник заданий ЕГЭ (1–27) для группировки вкладки теории ЕГЭ."""

    number = models.PositiveSmallIntegerField(unique=True, verbose_name="Номер задания ЕГЭ")
    title = models.CharField(max_length=200, verbose_name="Название задания")
    short_description = models.CharField(max_length=300, blank=True, verbose_name="Краткое описание")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ['number']
        verbose_name = "Задание ЕГЭ"
        verbose_name_plural = "Задания ЕГЭ"

    def __str__(self):
        return f"№{self.number}. {self.title}"


class Article(models.Model):
    """Статья учебника. Общая модель для обеих вкладок (дискриминатор track)."""

    TRACK_CHOICES = [
        ('material', 'Учебный материал'),
        ('ege', 'Теория ЕГЭ'),
    ]

    track = models.CharField(
        max_length=10, choices=TRACK_CHOICES, default='material',
        verbose_name="Вкладка"
    )
    section = models.ForeignKey(
        Section, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles', verbose_name="Блок (для учебного материала)"
    )
    ege_task = models.ForeignKey(
        EgeTask, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles', verbose_name="Задание ЕГЭ (для вкладки ЕГЭ)"
    )
    slug = models.SlugField(max_length=120, unique=True, verbose_name="URL-идентификатор")
    title = models.CharField(max_length=200, verbose_name="Заголовок статьи")
    description = models.TextField(blank=True, verbose_name="Краткое описание")
    thumbnail = models.ImageField(
        upload_to='textbook/articles/', blank=True, null=True,
        verbose_name="Превью изображение"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_published = models.BooleanField(default=False, verbose_name="Опубликовано")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ['order', 'title']
        verbose_name = "Статья"
        verbose_name_plural = "Статьи"
        indexes = [
            models.Index(fields=['track', 'is_published']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('textbook:article_detail', kwargs={'slug': self.slug})


class ArticleBlock(models.Model):
    """Семантический блок содержимого статьи (образец: spetskurs.TheoryBlock)."""

    BLOCK_TYPE_CHOICES = [
        ('text',    'Текст (Markdown)'),
        ('code',    'Код (только чтение)'),
        ('image',   'Изображение'),
        ('video',   'Видео'),
        ('formula', 'Формула (LaTeX)'),
        ('widget',  'Интерактивный виджет'),
    ]
    CODE_LANGUAGE_CHOICES = [
        ('python', 'Python'),
        ('cpp',    'C++'),
        ('c',      'C'),
        ('bash',   'Bash'),
        ('sql',    'SQL'),
    ]

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE,
        related_name='blocks', verbose_name="Статья"
    )
    block_type = models.CharField(
        max_length=20, choices=BLOCK_TYPE_CHOICES,
        default='text', verbose_name="Тип блока"
    )
    title = models.CharField(max_length=200, blank=True, verbose_name="Заголовок (необязательно)")
    content = models.TextField(
        blank=True, verbose_name="Содержимое",
        help_text="text — Markdown; code — исходный код; formula — LaTeX; "
                  "image/video — подпись/описание"
    )
    code_language = models.CharField(
        max_length=20, choices=CODE_LANGUAGE_CHOICES,
        default='python', blank=True, verbose_name="Язык кода"
    )
    image = models.ImageField(
        upload_to=article_image_upload, blank=True, null=True,
        verbose_name="Изображение"
    )
    video_url = models.URLField(
        blank=True, verbose_name="URL видео",
        help_text="YouTube, Vimeo или прямая ссылка"
    )
    widget_key = models.CharField(
        max_length=50, blank=True, verbose_name="Ключ виджета",
        help_text="Идентификатор компонента в реестре (напр. bits-viewer, embed)"
    )
    widget_config = models.JSONField(
        null=True, blank=True, verbose_name="Конфигурация виджета",
        help_text='Параметры в формате JSON, напр. {"value": 42, "bits": 8}'
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ['order']
        verbose_name = "Блок статьи"
        verbose_name_plural = "Блоки статьи"

    def __str__(self):
        return f"{self.article.title} — {self.get_block_type_display()} (#{self.order})"


class ArticleQuiz(models.Model):
    """Связь статьи с тестом самопроверки (переиспользуем quizzes.Quiz)."""

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE,
        related_name='self_check_quizzes', verbose_name="Статья"
    )
    quiz = models.ForeignKey(
        'quizzes.Quiz', on_delete=models.CASCADE,
        related_name='+', verbose_name="Тест самопроверки"
    )
    label = models.CharField(max_length=100, blank=True, verbose_name="Подпись (напр. «Разминка»)")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ['order']
        verbose_name = "Самопроверка статьи"
        verbose_name_plural = "Самопроверки статьи"
        constraints = [
            models.UniqueConstraint(fields=['article', 'quiz'], name='unique_article_quiz'),
        ]

    def __str__(self):
        return f"{self.article.title} → {self.quiz.title}"


class ArticleProgress(models.Model):
    """Прогресс ученика по статье (образец: quizzes.ExamTaskProgress)."""

    STATUS_CHOICES = [
        ('not_started', 'Не начато'),
        ('reading',     'Читается'),
        ('read',        'Прочитано'),
        ('mastered',    'Освоено'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='textbook_progress', verbose_name="Ученик"
    )
    article = models.ForeignKey(
        Article, on_delete=models.CASCADE,
        related_name='progress', verbose_name="Статья"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='reading',
        verbose_name="Статус"
    )
    first_opened_at = models.DateTimeField(auto_now_add=True, verbose_name="Впервые открыто")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Прочитано (долистано)")
    mastered_at = models.DateTimeField(null=True, blank=True, verbose_name="Освоено (самопроверка)")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Прогресс по статье"
        verbose_name_plural = "Прогресс по статьям"
        constraints = [
            models.UniqueConstraint(fields=['user', 'article'], name='unique_user_article_progress'),
        ]
        indexes = [
            models.Index(fields=['user', 'article']),
            models.Index(fields=['article', 'status']),
        ]

    def __str__(self):
        return f"{self.user} — {self.article} ({self.get_status_display()})"
