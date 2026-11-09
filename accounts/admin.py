from datetime import timedelta

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.utils import timezone

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


class StudentGroupForm(forms.ModelForm):
    """Код класса можно выпустить генератором или вписать свой: нормализуем
    (регистр, пробелы, дефисы), не даём двум классам один код, ставим срок."""

    class Meta:
        model = StudentGroup
        fields = '__all__'

    def clean_join_code(self):
        code = StudentGroup.normalize_code(self.cleaned_data.get('join_code'))
        taken = StudentGroup.objects.filter(join_code=code).exclude(pk=self.instance.pk)
        if code and taken.exists():
            raise forms.ValidationError(f'Этот код уже у класса «{taken.first().name}».')
        return code

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('join_code') and not cleaned.get('join_code_until'):
            cleaned['join_code_until'] = (timezone.now() +
                                          timedelta(days=StudentGroup.JOIN_CODE_DAYS))
        return cleaned


class StudentGroupAdmin(admin.ModelAdmin):
    form = StudentGroupForm
    search_fields = ['name']
    # Год выпуска – единственный переключатель «активный класс / архив»
    list_display = ('name', 'join_code_display', 'graduation_year', 'in_stats',
                    'no_textbook_deadlines', 'is_ege_class')
    list_editable = ('graduation_year', 'in_stats', 'no_textbook_deadlines', 'is_ege_class')
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
