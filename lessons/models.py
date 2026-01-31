from django.db import models


# Общие choices для шрифтов
FONT_SIZE_CHOICES = [
    ('text-sm', 'Маленький'),
    ('text-base', 'Обычный'),
    ('text-lg', 'Увеличенный'),
    ('text-xl', 'Большой'),
    ('text-2xl', 'Очень большой'),
    ('text-3xl', 'Огромный'),
]

FONT_FAMILY_CHOICES = [
    ('font-sans', 'Sans-serif (Inter)'),
    ('font-serif', 'Serif (Georgia)'),
    ('font-mono', 'Monospace'),
]

COLOR_CHOICES = [
    ('text-gray-900', 'Чёрный'),
    ('text-gray-700', 'Тёмно-серый'),
    ('text-gray-500', 'Серый'),
    ('text-white', 'Белый'),
    ('text-blue-600', 'Синий'),
    ('text-green-600', 'Зелёный'),
    ('text-red-600', 'Красный'),
    ('text-yellow-600', 'Жёлтый'),
    ('text-purple-600', 'Фиолетовый'),
    ('text-pink-600', 'Розовый'),
]

BG_COLOR_CHOICES = [
    ('bg-white', 'Белый'),
    ('bg-gray-50', 'Светло-серый'),
    ('bg-gray-100', 'Серый'),
    ('bg-blue-50', 'Светло-синий'),
    ('bg-green-50', 'Светло-зелёный'),
    ('bg-yellow-50', 'Светло-жёлтый'),
    ('bg-red-50', 'Светло-красный'),
    ('bg-purple-50', 'Светло-фиолетовый'),
]


class Section(models.Model):
    title = models.CharField(max_length=200, verbose_name="Название раздела")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ['order', 'title']
        verbose_name = "Раздел"
        verbose_name_plural = "Разделы"

    def __str__(self):
        return self.title

class Lesson(models.Model):
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, related_name='lessons', null=True, blank=True, verbose_name="Раздел")
    title = models.CharField(max_length=200, verbose_name="Тема урока")
    description = models.TextField(verbose_name="Описание и материалы", blank=True)
    file = models.FileField(upload_to='lessons_files/', blank=True, null=True, verbose_name="Файл с материалами")
    
    # Preview поля для карточек в списке уроков
    preview_image = models.ImageField(
        upload_to='lesson_previews/',
        blank=True,
        null=True,
        verbose_name="Превью изображение",
        help_text="Отображается в карточке урока в списке"
    )
    preview_description = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Краткое описание",
        help_text="Отображается в карточке урока (до 200 символов)"
    )
    
    # Заглушка для видео (на будущее)
    video_url = models.URLField(
        blank=True,
        verbose_name="URL видео",
        help_text="YouTube, Vimeo или прямая ссылка (на будущее)"
    )
    
    class Meta:
        verbose_name = "Урок"
        verbose_name_plural = "Уроки"
    
    def __str__(self):
        return self.title


class LessonBlock(models.Model):
    """Блок контента внутри урока."""
    
    BLOCK_TYPE_CHOICES = [
        ('text', 'Текст'),
        ('image', 'Изображение'),
        ('text_image', 'Текст + Изображение'),
    ]
    LAYOUT_CHOICES = [
        ('vertical', 'Вертикально'),
        ('horizontal', 'Горизонтально (текст слева)'),
        ('horizontal-reverse', 'Горизонтально (картинка слева)'),
    ]
    TEXT_ALIGN_CHOICES = [
        ('left', 'По левому краю'),
        ('center', 'По центру'),
        ('right', 'По правому краю'),
    ]
    IMAGE_ALIGN_CHOICES = [
        ('left', 'Слева'),
        ('center', 'По центру'),
        ('right', 'Справа'),
    ]
    
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='blocks',
        verbose_name="Урок"
    )
    block_type = models.CharField(
        max_length=20,
        choices=BLOCK_TYPE_CHOICES,
        default='text',
        verbose_name="Тип блока"
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Заголовок"
    )
    content = models.TextField(
        blank=True,
        verbose_name="Содержимое"
    )
    image = models.ImageField(
        upload_to='lessons_content/',
        blank=True,
        null=True,
        verbose_name="Изображение"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок отображения"
    )
    layout = models.CharField(
        max_length=20,
        choices=LAYOUT_CHOICES,
        default='vertical',
        verbose_name="Расположение"
    )
    image_width = models.PositiveIntegerField(
        default=100,
        verbose_name="Ширина изображения (%)"
    )
    image_height = models.PositiveIntegerField(
        default=0,
        verbose_name="Высота изображения (px)",
        help_text="0 = авто"
    )
    image_crop_x = models.FloatField(
        default=0,
        verbose_name="Crop X"
    )
    image_crop_y = models.FloatField(
        default=0,
        verbose_name="Crop Y"
    )
    image_crop_width = models.FloatField(
        default=0,
        verbose_name="Crop Width"
    )
    image_crop_height = models.FloatField(
        default=0,
        verbose_name="Crop Height"
    )
    image_natural_width = models.PositiveIntegerField(
        default=0,
        verbose_name="Image Natural Width"
    )
    image_natural_height = models.PositiveIntegerField(
        default=0,
        verbose_name="Image Natural Height"
    )
    text_pos_x = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Text X"
    )
    text_pos_y = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Text Y"
    )
    image_pos_x = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Image X"
    )
    image_pos_y = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Image Y"
    )
    image_align = models.CharField(
        max_length=10,
        choices=IMAGE_ALIGN_CHOICES,
        default='center',
        verbose_name="Выравнивание изображения"
    )
    text_align = models.CharField(
        max_length=10,
        choices=TEXT_ALIGN_CHOICES,
        default='left',
        verbose_name="Выравнивание текста"
    )
    
    # Настройки шрифтов заголовка
    title_font_size = models.CharField(
        max_length=20,
        choices=FONT_SIZE_CHOICES,
        default='text-xl',
        verbose_name="Размер заголовка"
    )
    title_font_family = models.CharField(
        max_length=20,
        choices=FONT_FAMILY_CHOICES,
        default='font-sans',
        verbose_name="Шрифт заголовка"
    )
    title_color = models.CharField(
        max_length=30,
        choices=COLOR_CHOICES,
        default='text-gray-900',
        verbose_name="Цвет заголовка"
    )
    
    # Настройки шрифтов контента
    content_font_size = models.CharField(
        max_length=20,
        choices=FONT_SIZE_CHOICES,
        default='text-base',
        verbose_name="Размер текста"
    )
    content_font_family = models.CharField(
        max_length=20,
        choices=FONT_FAMILY_CHOICES,
        default='font-sans',
        verbose_name="Шрифт текста"
    )
    content_color = models.CharField(
        max_length=30,
        choices=COLOR_CHOICES,
        default='text-gray-700',
        verbose_name="Цвет текста"
    )
    
    # Фон карточки
    card_bg = models.CharField(
        max_length=30,
        choices=BG_COLOR_CHOICES,
        default='bg-white',
        verbose_name="Фон карточки"
    )
    
    class Meta:
        ordering = ['order']
        verbose_name = "Блок урока"
        verbose_name_plural = "Блоки урока"
    
    def __str__(self):
        return f"{self.lesson.title} - {self.get_block_type_display()} (#{self.order})"
