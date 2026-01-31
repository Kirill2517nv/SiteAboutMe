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


class ContentBlock(models.Model):
    """Универсальный блок контента для главной страницы и страницы 'Обо мне'."""
    
    PAGE_CHOICES = [
        ('home', 'Главная'),
        ('about', 'Обо мне'),
    ]
    BLOCK_TYPE_CHOICES = [
        ('text', 'Текст'),
        ('image', 'Изображение'),
        ('text_image', 'Текст + Изображение'),
    ]
    
    page = models.CharField(
        max_length=20,
        choices=PAGE_CHOICES,
        verbose_name="Страница"
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
        verbose_name="Заголовок",
        help_text="Для главной страницы - заголовок карточки"
    )
    content = models.TextField(
        blank=True,
        verbose_name="Содержимое"
    )
    image = models.ImageField(
        upload_to='content/',
        blank=True,
        null=True,
        verbose_name="Изображение"
    )
    link_url = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="URL ссылки",
        help_text="Для главной страницы - ссылка на раздел"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок отображения"
    )
    # Настройки layout
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
    layout = models.CharField(
        max_length=20,
        choices=LAYOUT_CHOICES,
        default='vertical',
        verbose_name="Расположение"
    )
    image_width = models.PositiveIntegerField(
        default=100,
        verbose_name="Ширина изображения (%)",
        help_text="Процент ширины для изображения (10-100)"
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
    
    # Дополнительные настройки изображения
    OBJECT_FIT_CHOICES = [
        ('cover', 'Заполнить (cover)'),
        ('contain', 'Вместить (contain)'),
        ('fill', 'Растянуть (fill)'),
        ('none', 'Оригинал (none)'),
    ]
    image_object_fit = models.CharField(
        max_length=20,
        choices=OBJECT_FIT_CHOICES,
        default='cover',
        verbose_name="Заполнение изображения"
    )
    image_border_radius = models.CharField(
        max_length=20,
        default='0.5rem',
        verbose_name="Скругление углов изображения"
    )
    image_opacity = models.PositiveIntegerField(
        default=100,
        verbose_name="Прозрачность изображения (%)"
    )
    image_position_x = models.PositiveIntegerField(
        default=50,
        verbose_name="Позиция фокуса X (%)",
        help_text="0 = левый край, 50 = центр, 100 = правый край"
    )
    image_position_y = models.PositiveIntegerField(
        default=50,
        verbose_name="Позиция фокуса Y (%)",
        help_text="0 = верхний край, 50 = центр, 100 = нижний край"
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
        ordering = ['page', 'order']
        verbose_name = "Блок контента"
        verbose_name_plural = "Блоки контента"
    
    def __str__(self):
        return f"{self.get_page_display()} - {self.title or self.get_block_type_display()} (#{self.order})"
