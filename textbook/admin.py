from django.contrib import admin

from .models import (
    Article,
    ArticleBlock,
    ArticleProgress,
    ArticleQuiz,
    EgeTask,
    Section,
    SectionExtension,
)


class ArticleBlockInline(admin.StackedInline):
    model = ArticleBlock
    extra = 1
    ordering = ('order',)
    fields = (
        'order', 'block_type', 'title', 'content',
        'code_language', 'image', 'video_url',
        'widget_key', 'widget_config',
    )


class ArticleQuizInline(admin.TabularInline):
    model = ArticleQuiz
    extra = 1
    ordering = ('order',)
    autocomplete_fields = ('quiz',)
    fields = ('order', 'quiz', 'label')


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'is_published', 'deadline', 'grades_summary')
    list_filter = ('is_published',)
    list_editable = ('order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}
    autocomplete_fields = ('practicum_quiz',)
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'description', 'thumbnail', 'order', 'is_published')}),
        ('Задачи блока', {'fields': ('practicum_quiz', 'deadline', 'hints_open')}),
        ('Оценка за блок', {
            'fields': ('grade_5_from', 'grade_4_from', 'grade_3_from'),
            'description': 'Сколько задач практикума нужно решить на каждую оценку. '
                           'Если «Оценка 3» не заполнена, оценка за блок не выставляется. '
                           'Всё, что ниже порога тройки, считается двойкой.',
        }),
    )

    @admin.display(description='Оценки')
    def grades_summary(self, obj):
        if obj.grade_3_from is None:
            return '–'
        return f'5: от {obj.grade_5_from} · 4: от {obj.grade_4_from} · 3: от {obj.grade_3_from}'


@admin.register(SectionExtension)
class SectionExtensionAdmin(admin.ModelAdmin):
    """Кому продлён дедлайн. Список отвечает и «кому», и «по какому блоку»."""

    list_display = ('user', 'section', 'deadline', 'reason')
    list_filter = ('section',)
    list_editable = ('deadline',)
    search_fields = ('user__username', 'user__last_name', 'user__first_name', 'reason')
    autocomplete_fields = ('user',)


@admin.register(EgeTask)
class EgeTaskAdmin(admin.ModelAdmin):
    # Порог правится прямо в списке: это настройка на каждый день,
    # ради неё заходить в карточку задания незачем.
    list_display = ('number', 'title', 'classroom_enabled', 'exam_unlock_threshold',
                    'exam_size', 'order')
    list_editable = ('classroom_enabled', 'exam_unlock_threshold', 'exam_size', 'order')
    ordering = ('number',)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'track', 'section', 'ege_task', 'course_task', 'order', 'is_published')
    list_filter = ('track', 'is_published', 'section', 'ege_task', 'course_task')
    list_editable = ('order', 'is_published')
    search_fields = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ArticleBlockInline, ArticleQuizInline]
    fieldsets = (
        (None, {
            'fields': ('track', 'title', 'slug', 'description', 'order', 'is_published'),
        }),
        ('Привязка (выбирается по вкладке)', {
            'fields': ('section', 'ege_task', 'course_task'),
            'description': 'Для «Учебного материала» укажите Блок; для «Теории ЕГЭ» – Задание ЕГЭ; '
                           'для «Спецкурса» – Задачу спецкурса (пусто = статья из «Основ C++»).',
        }),
        ('Превью', {
            'fields': ('thumbnail',),
            'classes': ('collapse',),
        }),
    )


@admin.register(ArticleProgress)
class ArticleProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'article', 'status', 'first_opened_at', 'read_at', 'mastered_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'article__title')
    readonly_fields = ('first_opened_at', 'updated_at')
