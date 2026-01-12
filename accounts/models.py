from django.db import models
from django.contrib.auth.models import User

class StudentGroup(models.Model):
    name = models.CharField(max_length=50, verbose_name="Название группы (класса)")
    
    class Meta:
        verbose_name = "Учебный класс"
        verbose_name_plural = "Учебные классы"

    def __str__(self):
        return self.name

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name="Пользователь")
    group = models.ForeignKey(StudentGroup, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Класс", related_name='students')
    
    class Meta:
        verbose_name = "Профиль ученика"
        verbose_name_plural = "Профили учеников"

    def __str__(self):
        return f"Профиль: {self.user.username}"
