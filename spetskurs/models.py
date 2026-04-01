from django.db import models
from django.urls import reverse


class TheoryPage(models.Model):
    SEMESTER_CHOICES = [(1, 'Семестр 1'), (2, 'Семестр 2')]

    slug = models.SlugField(max_length=100, unique=True, verbose_name="URL-идентификатор")
    title = models.CharField(max_length=200, verbose_name="Заголовок")
    description = models.TextField(blank=True, verbose_name="Краткое описание")
    thumbnail = models.ImageField(
        upload_to='spetskurs/theory/', blank=True, null=True,
        verbose_name="Превью изображение"
    )
    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, default=1, verbose_name="Семестр"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_published = models.BooleanField(default=False, verbose_name="Опубликовано")

    class Meta:
        ordering = ['semester', 'order']
        verbose_name = "Страница теории"
        verbose_name_plural = "Страницы теории"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('spetskurs:theory_detail', kwargs={'slug': self.slug})


class TheoryBlock(models.Model):
    BLOCK_TYPE_CHOICES = [
        ('text',    'Текст'),
        ('formula', 'Формула (LaTeX)'),
        ('code',    'Код'),
        ('image',   'Изображение'),
    ]
    CODE_LANGUAGE_CHOICES = [
        ('cpp',    'C++'),
        ('c',      'C'),
        ('python', 'Python'),
        ('bash',   'Bash'),
    ]

    theory_page = models.ForeignKey(
        TheoryPage, on_delete=models.CASCADE,
        related_name='blocks', verbose_name="Страница теории"
    )
    block_type = models.CharField(
        max_length=20, choices=BLOCK_TYPE_CHOICES,
        default='text', verbose_name="Тип блока"
    )
    title = models.CharField(max_length=200, blank=True, verbose_name="Заголовок (необязательно)")
    content = models.TextField(blank=True, verbose_name="Содержимое")
    code_language = models.CharField(
        max_length=20, choices=CODE_LANGUAGE_CHOICES,
        default='cpp', blank=True, verbose_name="Язык кода"
    )
    image = models.ImageField(
        upload_to='spetskurs/theory/images/', blank=True, null=True,
        verbose_name="Изображение"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ['order']
        verbose_name = "Блок теории"
        verbose_name_plural = "Блоки теории"

    def __str__(self):
        return f"{self.theory_page.title} — {self.get_block_type_display()} (#{self.order})"


class Simulation(models.Model):
    SEMESTER_CHOICES = [(1, 'Семестр 1'), (2, 'Семестр 2')]

    slug = models.SlugField(max_length=100, unique=True, verbose_name="URL-идентификатор")
    title = models.CharField(max_length=200, verbose_name="Название симуляции")
    description = models.TextField(blank=True, verbose_name="Описание")
    thumbnail = models.ImageField(
        upload_to='spetskurs/simulations/', blank=True, null=True,
        verbose_name="Превью изображение"
    )
    html_path = models.CharField(
        max_length=300, blank=True, verbose_name="Путь к HTML-файлу симуляции",
        help_text="Относительный путь в static/, например: spetskurs/wasm/pendulum.html"
    )
    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, default=1, verbose_name="Семестр"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_published = models.BooleanField(default=False, verbose_name="Опубликовано")

    class Meta:
        ordering = ['semester', 'order']
        verbose_name = "Симуляция"
        verbose_name_plural = "Симуляции"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('spetskurs:simulation_detail', kwargs={'slug': self.slug})
