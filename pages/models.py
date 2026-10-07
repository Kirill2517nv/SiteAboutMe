from django.db import models


class AuthorProfile(models.Model):
    full_name = models.CharField(max_length=200, verbose_name="Полное имя")
    role = models.CharField(max_length=300, verbose_name="Должность / аффилиация")
    bio = models.TextField(blank=True, verbose_name="О себе")
    research_interests = models.TextField(blank=True, verbose_name="Научные интересы")
    portrait = models.ImageField(
        upload_to='about/portrait/',
        blank=True, null=True,
        verbose_name="Портрет (hero)"
    )
    email = models.EmailField(blank=True, verbose_name="Email")
    telegram_url = models.URLField(blank=True, verbose_name="Ссылка Telegram")
    vk_url = models.URLField(blank=True, verbose_name="Ссылка ВКонтакте")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Профиль автора"
        verbose_name_plural = "Профиль автора"

    def __str__(self):
        return self.full_name


class AuthorPhoto(models.Model):
    image = models.ImageField(upload_to='about/photos/', verbose_name="Фото")
    caption = models.CharField(max_length=200, blank=True, verbose_name="Подпись")
    alt_text = models.CharField(max_length=200, blank=True, verbose_name="Alt-текст")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Порядок")
    is_visible = models.BooleanField(default=True, verbose_name="Отображать")

    class Meta:
        ordering = ['order']
        verbose_name = "Фото автора"
        verbose_name_plural = "Фотографии автора"

    def __str__(self):
        return f"Фото #{self.order} – {self.caption or self.image.name}"


class AuthorVideo(models.Model):
    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    video_file = models.FileField(upload_to='about/videos/', verbose_name="Видеофайл (MP4)")
    poster = models.ImageField(
        upload_to='about/video_posters/',
        blank=True, null=True,
        verbose_name="Постер (превью)"
    )
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Порядок")
    is_visible = models.BooleanField(default=True, verbose_name="Отображать")

    class Meta:
        ordering = ['order']
        verbose_name = "Видео автора"
        verbose_name_plural = "Видео автора"

    def __str__(self):
        return f"#{self.order} {self.title}"


class AuthorEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('education', 'Образование'),
        ('publication', 'Публикация'),
        ('conference', 'Конференция'),
        ('award', 'Награда / грант'),
    ]

    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        verbose_name="Тип события"
    )
    year = models.PositiveSmallIntegerField(verbose_name="Год")
    is_current = models.BooleanField(
        default=False,
        verbose_name="Настоящее время",
        help_text="Показывать «настоящее время» вместо конечного года"
    )
    month = models.PositiveSmallIntegerField(
        blank=True, null=True,
        verbose_name="Месяц (1–12)"
    )
    title = models.CharField(max_length=300, verbose_name="Заголовок")
    subtitle = models.CharField(max_length=300, blank=True, verbose_name="Подзаголовок")
    description = models.TextField(blank=True, verbose_name="Описание")
    doi_or_url = models.URLField(blank=True, verbose_name="DOI / ссылка")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Порядок")
    is_visible = models.BooleanField(default=True, verbose_name="Отображать")

    class Meta:
        ordering = ['-year', 'order']
        verbose_name = "Событие / публикация"
        verbose_name_plural = "События / публикации"

    def __str__(self):
        return f"[{self.get_event_type_display()}] {self.year} – {self.title}"
