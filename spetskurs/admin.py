from django.contrib import admin
from .models import TheoryPage, TheoryBlock, Simulation


class TheoryBlockInline(admin.StackedInline):
    model = TheoryBlock
    extra = 1
    ordering = ('order',)
    fields = ('order', 'block_type', 'title', 'content', 'code_language', 'image')


@admin.register(TheoryPage)
class TheoryPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'semester', 'order', 'is_published')
    list_filter = ('semester', 'is_published')
    list_editable = ('order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [TheoryBlockInline]
    fieldsets = (
        (None, {
            'fields': ('slug', 'title', 'description', 'semester', 'order', 'is_published')
        }),
        ('Превью', {
            'fields': ('thumbnail',),
            'classes': ('collapse',),
        }),
    )


@admin.register(Simulation)
class SimulationAdmin(admin.ModelAdmin):
    list_display = ('title', 'semester', 'order', 'is_published', 'html_path')
    list_filter = ('semester', 'is_published')
    list_editable = ('order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}
    fieldsets = (
        (None, {
            'fields': ('slug', 'title', 'description', 'semester', 'order', 'is_published')
        }),
        ('Файл симуляции', {
            'fields': ('html_path',),
            'description': 'Укажите путь к .html файлу относительно static/, например: spetskurs/wasm/pendulum.html'
        }),
        ('Превью', {
            'fields': ('thumbnail',),
            'classes': ('collapse',),
        }),
    )
