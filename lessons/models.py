from django.db import models

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
    description = models.TextField(verbose_name="Описание и материалы")
    file = models.FileField(upload_to='lessons_files/', blank=True, null=True, verbose_name="Файл с материалами")
    
    def __str__(self):
        return self.title
