from django.contrib import admin
from .models import ContentBlock


@admin.register(ContentBlock)
class ContentBlockAdmin(admin.ModelAdmin):
    list_display = ('page', 'block_type', 'title', 'order')
    list_filter = ('page', 'block_type')
    list_editable = ('order',)
    search_fields = ('title', 'content')
    ordering = ('page', 'order')
