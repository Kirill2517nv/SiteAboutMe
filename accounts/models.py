from django.db import models
from django.contrib.auth.models import User

class StudentGroup(models.Model):
    name = models.CharField(max_length=50, verbose_name="Название группы (класса)")
    # ponytail: год выпуска – он же флаг архива. Отдельный is_archived не нужен:
    # выпускаются классами целиком, а заполненный год сразу даёт и заголовок,
    # и группировку на странице выпускников.
    graduation_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Год выпуска",
        help_text="Заполнено – класс уходит в архив выпускников и пропадает из активных списков",
    )
    graduation_photo = models.ImageField(
        upload_to='alumni/', blank=True, verbose_name="Общее фото класса",
    )
    graduation_note = models.TextField(
        blank=True, verbose_name="Слово учителя о классе",
    )
    
    class Meta:
        verbose_name = "Учебный класс"
        verbose_name_plural = "Учебные классы"

    @property
    def is_archived(self):
        return self.graduation_year is not None

    def __str__(self):
        return f"{self.name} (выпуск {self.graduation_year})" if self.graduation_year else self.name

class Profile(models.Model):
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

    class Meta:
        verbose_name = "Профиль ученика"
        verbose_name_plural = "Профили учеников"

    @property
    def is_alumni(self):
        return bool(self.group and self.group.graduation_year)

    def __str__(self):
        return f"Профиль: {self.user.username}"
