from django.contrib import admin

from .models import CourseTask


@admin.register(CourseTask)
class CourseTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'number', 'semester', 'order', 'is_published', 'html_path')
    list_filter = ('semester', 'is_published')
    list_editable = ('number', 'order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}
    fieldsets = (
        (None, {
            'fields': ('slug', 'title', 'number', 'description',
                       'semester', 'order', 'is_published')
        }),
        ('Симуляция', {
            'fields': ('html_path', 'frame_width', 'frame_height'),
            'description': 'Путь к .html относительно static/, например: '
                           'spetskurs/wasm/Task_2.html. Пропорция кадра – под окно '
                           'задачи: Task_2 вертикальная (850x1200), Task_3 – 1200x800.'
        }),
        ('Исходник', {
            'fields': ('code_url',),
        }),
        ('Превью', {
            'fields': ('thumbnail',),
            'classes': ('collapse',),
        }),
    )
    # Статьи задачи редактируются в админке учебника (textbook.Article с
    # track='spetskurs'): это одна модель на весь сайт, и второй набор инлайнов
    # к ней разошёлся бы с основным при первой же правке.
