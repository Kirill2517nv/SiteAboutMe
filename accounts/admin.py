from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Notification, StudentGroup, Profile

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
    list_display = ('name', 'graduation_year', 'in_stats', 'no_textbook_deadlines')
    list_editable = ('graduation_year', 'in_stats', 'no_textbook_deadlines')

# Перерегистрируем User с новыми настройками
admin.site.unregister(User)
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
