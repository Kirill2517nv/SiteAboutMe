from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.utils import timezone

from .models import JoinRequest, Notification, StudentGroup, Profile, accept_join

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Профиль ученика'

# Переопределяем админку пользователя, чтобы видеть Профиль прямо внутри Пользователя
class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)
    list_display = ('username', 'last_name', 'first_name', 'is_staff', 'is_active', 'email')
    search_fields = ('last_name', 'first_name', 'username', 'email')
    list_filter = BaseUserAdmin.list_filter + ('profile__group', 'profile__is_ege')

class StudentGroupAdmin(admin.ModelAdmin):
    search_fields = ['name']
    # Год выпуска – единственный переключатель «активный класс / архив»
    list_display = ('name', 'join_code_display', 'graduation_year', 'in_stats',
                    'no_textbook_deadlines', 'is_ege_class')
    list_editable = ('graduation_year', 'in_stats', 'no_textbook_deadlines', 'is_ege_class')
    # Код генерирует действие, вручную – только срок
    readonly_fields = ('join_code',)
    actions = ['issue_code', 'close_code']

    @admin.display(description='Код класса')
    def join_code_display(self, obj):
        if not obj.join_code:
            return '–'
        if obj.join_code_until and obj.join_code_until > timezone.now():
            until = timezone.localtime(obj.join_code_until).strftime('%d.%m %H:%M')
            return f'{obj.join_code} до {until}'
        return f'{obj.join_code} (истёк)'

    @admin.action(description=f'Выпустить новый код на {StudentGroup.JOIN_CODE_DAYS} дней '
                              '(старый перестанет работать)')
    def issue_code(self, request, queryset):
        for group in queryset:
            group.issue_join_code()
        codes = ', '.join(f'{g.name}: {g.join_code}' for g in queryset.order_by('name'))
        self.message_user(request, f'Новые коды – {codes}')

    @admin.action(description='Закрыть код')
    def close_code(self, request, queryset):
        for group in queryset:
            group.close_join_code()
        self.message_user(request, f'Коды закрыты: {queryset.count()}')


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    """Заявки по коду класса. Принятый ученик уходит отсюда в свой класс,
    отклонённый удаляется вместе с аккаунтом."""

    list_display = ('last_name', 'first_name', 'username', 'join_class', 'date_joined')
    list_filter = ('profile__join_group',)
    search_fields = ('last_name', 'first_name', 'username')
    ordering = ('profile__join_group__name', 'last_name', 'first_name')
    actions = ['accept', 'accept_ege', 'reject']
    fields = ('last_name', 'first_name', 'username', 'date_joined')

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .filter(is_active=False, profile__join_group__isnull=False)
                .select_related('profile__join_group'))

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)  # «Отклонить» и есть удаление
        return actions

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Класс', ordering='profile__join_group__name')
    def join_class(self, obj):
        group = obj.profile.join_group
        return f'{group.name} (ЕГЭ)' if group.is_ege_class else group.name

    @admin.action(description='Принять')
    def accept(self, request, queryset):
        for user in queryset:
            accept_join(user)
        self.message_user(request, f'Принято: {len(queryset)}')

    @admin.action(description='Принять, сдаёт ЕГЭ')
    def accept_ege(self, request, queryset):
        for user in queryset:
            accept_join(user, ege=True)
        self.message_user(request, f'Принято со «Сдаёт ЕГЭ»: {len(queryset)}')

    @admin.action(description='Отклонить (аккаунт удаляется)')
    def reject(self, request, queryset):
        User.objects.filter(pk__in=[u.pk for u in queryset]).delete()
        self.message_user(request, f'Отклонено заявок: {len(queryset)}')

# Перерегистрируем User с новыми настройками
admin.site.unregister(User)
# Группы прав не используются (0 групп), а в меню стояли рядом с «Учебными классами»
admin.site.unregister(Group)
admin.site.register(User, UserAdmin)

admin.site.register(StudentGroup, StudentGroupAdmin)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Только просмотр: уведомления пишут сами действия учителя."""
    list_display = ('user', 'text', 'created_at', 'read_at')
    list_filter = ('read_at',)
    search_fields = ('user__last_name', 'user__username', 'text')
    list_select_related = ('user',)
    readonly_fields = ('user', 'text', 'url', 'created_at', 'read_at')
