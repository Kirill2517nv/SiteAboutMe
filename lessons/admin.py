from django.contrib import admin
from .models import Lesson, Section, LessonBlock, LessonAttachment


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'order')
    ordering = ('order', 'title')


class LessonBlockInline(admin.TabularInline):
    model = LessonBlock
    extra = 1
    ordering = ('order',)


class LessonAttachmentInline(admin.TabularInline):
    model = LessonAttachment
    extra = 1
    ordering = ('order',)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'section', 'has_preview', 'has_presentation', 'attachment_count')
    list_filter = ('section',)
    inlines = [LessonAttachmentInline, LessonBlockInline]
    fieldsets = (
        (None, {
            'fields': ('title', 'section', 'description')
        }),
        ('Презентация Slidev', {
            'fields': ('presentation_url', 'presentation_title', 'presentation_pdf'),
            'classes': ('collapse',),
        }),
        ('Превью для карточки', {
            'fields': ('preview_image', 'preview_description'),
            'classes': ('collapse',),
            'description': 'Эти поля отображаются в карточке урока на странице списка уроков'
        }),
        ('Видео (на будущее)', {
            'fields': ('video_url',),
            'classes': ('collapse',),
        }),
    )

    @admin.display(boolean=True, description='Превью')
    def has_preview(self, obj):
        return bool(obj.preview_image)

    @admin.display(boolean=True, description='Презентация')
    def has_presentation(self, obj):
        return bool(obj.presentation_url)

    @admin.display(description='Файлов')
    def attachment_count(self, obj):
        return obj.attachments.count()


@admin.register(LessonBlock)
class LessonBlockAdmin(admin.ModelAdmin):
    list_display = ('lesson', 'block_type', 'order')
    list_filter = ('lesson', 'block_type')
    list_editable = ('order',)
    ordering = ('lesson', 'order')
