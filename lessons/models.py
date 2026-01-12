from django.db import models

class Lesson(models.Model):
    title = models.CharField(max_length=200, verbose_name="Тема урока")
    description = models.TextField(verbose_name="Описание и материалы")
    file = models.FileField(upload_to='lessons_files/', blank=True, null=True, verbose_name="Файл с материалами")
    
    def __str__(self):
        return self.title

