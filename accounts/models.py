from django.db import models
from django.contrib.auth.models import User

class StudentGroup(models.Model):
    name = models.CharField(max_length=50, verbose_name="Название группы (класса)")
    # ponytail: год выпуска – он же флаг архива. Отдельный is_archived не нужен:
    # выпускаются классами целиком, а заполненный год сразу даёт и заголовок,
    # и группировку на странице выпускников.
    graduation_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Год выпуска",
        help_text="Заполнено – класс появляется в архиве выпускников. "
                  "Из статистики его убирает только галочка «В статистике»",
    )
    graduation_photo = models.ImageField(
        upload_to='alumni/', blank=True, verbose_name="Общее фото класса",
    )
    graduation_note = models.TextField(
        blank=True, verbose_name="Слово учителя о классе",
    )
    no_textbook_deadlines = models.BooleanField(
        default=False, verbose_name="Без дедлайнов учебника",
        help_text="Блоки учебника у учеников этого класса не закрываются по сроку – "
                  "например, у группы подготовки к ЕГЭ, где учебник – справочник.",
    )
    in_stats = models.BooleanField(
        default=True, verbose_name="В статистике",
        help_text="Снято – вкладки класса нет на страницах статистики учителя "
                  "(учебник, ЕГЭ). Для классов, с которыми сейчас не работаете.",
    )

    class Meta:
        verbose_name = "Учебный класс"
        verbose_name_plural = "Учебные классы"

    @classmethod
    def in_stats_groups(cls):
        """Классы, которые учитель видит в статистике. Выпуск на это не влияет."""
        return cls.objects.filter(in_stats=True)

    @property
    def is_archived(self):
        return self.graduation_year is not None

    def __str__(self):
        return f"{self.name} (выпуск {self.graduation_year})" if self.graduation_year else self.name

class Profile(models.Model):
    # Кто видит имя ученика под его решениями в «Решениях других». Само решение
    # видно всем, кто решил задачу, – прячется только подпись. Переопределяется
    # у отдельного решения (quizzes.SharedSolution.name_visibility).
    NAME_VISIBILITY_CHOICES = [
        ('anon', 'Никому – подписывать «Ученик №…»'),
        ('class', 'Только моему классу'),
        ('all', 'Всем'),
    ]
    # Те же значения для плиток выбора – (значение, значок, заголовок, подпись).
    # Один список на профиль и галерею: подписи не расходятся.
    NAME_VISIBILITY_OPTIONS = [
        ('anon', '🕶️', 'Никто', 'Вместо имени – «Ученик №…»'),
        ('class', '👥', 'Мой класс', 'Одноклассники видят имя, остальные – «Ученик №…»'),
        ('all', '🌍', 'Все', 'Имя видят все ученики сайта'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name="Пользователь")
    group = models.ForeignKey(StudentGroup, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Класс", related_name='students')
    is_ege = models.BooleanField(default=False, verbose_name="Сдаёт ЕГЭ")
    avatar = models.ImageField(upload_to='avatars/', blank=True, verbose_name="Аватар")
    # Карточку выпускника заполняет сам ученик – учитель её не редактирует.
    # Внимание: имя и аватар на /alumni/ показываются у всех учеников класса
    # с проставленным годом выпуска, независимо от этих полей. Согласие на
    # публикацию класса даёт учитель, проставляя год.
    alumni_place = models.CharField(
        max_length=200, blank=True, verbose_name="Вуз",
    )
    alumni_about = models.TextField(blank=True, verbose_name="О себе")
    solution_name_visibility = models.CharField(
        max_length=5, choices=NAME_VISIBILITY_CHOICES, default='anon',
        verbose_name="Имя под решениями",
    )

    class Meta:
        verbose_name = "Профиль ученика"
        verbose_name_plural = "Профили учеников"

    @property
    def is_alumni(self):
        return bool(self.group and self.group.graduation_year)

    def __str__(self):
        return f"Профиль: {self.user.username}"


class Notification(models.Model):
    """
    Уведомление ученику: учитель ответил – на разбор в «Решениях других» или на
    правку к статье. Колокольчик в шапке считает непрочитанные, страница
    /accounts/notifications/ отмечает их прочитанными при открытии.

    Одна модель на все поводы: текст и ссылку собирает тот, кто уведомляет,
    – иначе каждый новый повод заводил бы свой счётчик в шапке.
    """
    # Раздел на странице уведомлений. Порядок здесь – порядок разделов там.
    KIND_CHOICES = [
        ('suggestion', 'Ваши правки к статьям'),
        ('solution', 'Ваши комментарии к задачам'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', verbose_name="Кому")
    # Цвет плашки: зелёная – принято, красная – отклонено, жёлтая – ответ без решения.
    STATUS_CHOICES = [
        ('accepted', 'Принято'),
        ('rejected', 'Отклонено'),
        ('pending', 'На рассмотрении'),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name="Раздел")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Решение")
    text = models.CharField(max_length=300, verbose_name="Текст")
    url = models.CharField(max_length=300, blank=True, verbose_name="Ссылка")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Прочитано")

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'read_at'])]

    def __str__(self):
        return f"{self.user.username}: {self.text}"


def notify(user, kind, text, url='', status='pending'):
    """Уведомить ученика. Учителю не пишем: ответы даёт он сам."""
    if user.is_superuser:
        return None
    return Notification.objects.create(user=user, kind=kind, status=status, text=text[:300], url=url)
