from django.contrib import admin

from .models import (
    Article,
    ArticleBlock,
    ArticleProgress,
    ArticleQuiz,
    EgeTask,
    Section,
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
    list_display = ('title', 'order', 'is_published')
    list_filter = ('is_published',)
    list_editable = ('order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(EgeTask)
class EgeTaskAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'order')
    list_editable = ('order',)
    ordering = ('number',)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'track', 'section', 'ege_task', 'order', 'is_published')
    list_filter = ('track', 'is_published', 'section', 'ege_task')
    list_editable = ('order', 'is_published')
    search_fields = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ArticleBlockInline, ArticleQuizInline]
    fieldsets = (
        (None, {
            'fields': ('track', 'title', 'slug', 'description', 'order', 'is_published'),
        }),
        ('Привязка (выбирается по вкладке)', {
            'fields': ('section', 'ege_task'),
            'description': 'Для «Учебного материала» укажите Блок; для «Теории ЕГЭ» — Задание ЕГЭ.',
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
