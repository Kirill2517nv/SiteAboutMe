from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import StudentGroup, Profile

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Профиль ученика'

# Переопределяем админку пользователя, чтобы видеть Профиль прямо внутри Пользователя
class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)
    search_fields = ('last_name', 'first_name', 'username', 'email')

class StudentGroupAdmin(admin.ModelAdmin):
    search_fields = ['name']

# Перерегистрируем User с новыми настройками
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.register(StudentGroup, StudentGroupAdmin)
