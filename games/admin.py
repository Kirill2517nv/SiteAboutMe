from django.contrib import admin
from .models import Category, Question, QuestionMedia, GamePack, GamePackCategory, GameSession


class QuestionMediaInline(admin.TabularInline):
    model = QuestionMedia
    extra = 1
    fields = ('media_type', 'file', 'order')


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ('text', 'answer', 'points', 'order')
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('title', 'created_by__username', 'created_by__last_name')
    list_select_related = ('created_by',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [QuestionInline]
    fieldsets = (
        (None, {'fields': ('title', 'description', 'created_by', 'status', 'moderator_comment')}),
        ('Мета', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    actions = ['approve_categories', 'reject_categories']

    @admin.action(description='Одобрить выбранные темы')
    def approve_categories(self, request, queryset):
        updated = queryset.update(status='approved')
        self.message_user(request, f'Одобрено тем: {updated}')

    @admin.action(description='Отклонить выбранные темы')
    def reject_categories(self, request, queryset):
        updated = queryset.update(status='rejected')
        self.message_user(request, f'Отклонено тем: {updated}')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text_preview', 'category', 'points', 'order')
    list_filter = ('category__status',)
    search_fields = ('text', 'answer', 'category__title')
    list_select_related = ('category',)
    inlines = [QuestionMediaInline]

    @admin.display(description='Вопрос')
    def text_preview(self, obj):
        return obj.text[:60] + '…' if len(obj.text) > 60 else obj.text


class GamePackCategoryInline(admin.TabularInline):
    model = GamePackCategory
    extra = 0
    fields = ('category', 'order')
    raw_id_fields = ('category',)


@admin.register(GamePack)
class GamePackAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'is_public', 'category_count', 'created_at')
    list_filter = ('is_public',)
    search_fields = ('title',)
    list_select_related = ('created_by',)
    inlines = [GamePackCategoryInline]

    @admin.display(description='Тем')
    def category_count(self, obj):
        return obj.pack_categories.count()


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'game_pack', 'created_by', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'game_pack')
    list_select_related = ('game_pack', 'created_by')
    readonly_fields = ('board_state', 'players', 'created_at', 'updated_at')
