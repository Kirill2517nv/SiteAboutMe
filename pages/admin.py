from django.contrib import admin
from .models import AuthorProfile, AuthorPhoto, AuthorVideo, AuthorEvent


@admin.register(AuthorProfile)
class AuthorProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'role', 'is_active')
    fieldsets = (
        ('Основное', {
            'fields': ('full_name', 'role', 'portrait', 'bio', 'research_interests', 'is_active')
        }),
        ('Контакты', {
            'fields': ('email', 'telegram_url', 'vk_url')
        }),
    )


@admin.register(AuthorPhoto)
class AuthorPhotoAdmin(admin.ModelAdmin):
    list_display = ('caption', 'order', 'is_visible')
    list_display_links = ('caption',)
    list_editable = ('order', 'is_visible')
    ordering = ('order',)


@admin.register(AuthorVideo)
class AuthorVideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'is_visible')
    list_display_links = ('title',)
    list_editable = ('order', 'is_visible')
    ordering = ('order',)


@admin.register(AuthorEvent)
class AuthorEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'year', 'title', 'order', 'is_visible')
    list_filter = ('event_type',)
    list_editable = ('order', 'is_visible')
    search_fields = ('title', 'subtitle', 'description')
    ordering = ('-year', 'order')
