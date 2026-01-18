from django.contrib import admin
from .models import Lesson, Section

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'order')
    ordering = ('order', 'title')

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'section')
    list_filter = ('section',)
