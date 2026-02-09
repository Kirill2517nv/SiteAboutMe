from django.contrib import admin
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from .models import Quiz, Question, Choice, UserResult, UserAnswer, TestCase, QuizAssignment, HelpRequest, HelpComment
from .forms import BulkQuizAssignmentForm

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4

class TestCaseInline(admin.StackedInline):
    model = TestCase
    extra = 1

class QuestionAdmin(admin.ModelAdmin):
    list_display = ('title', 'quiz', 'question_type')
    list_filter = ('quiz', 'question_type')
    search_fields = ('title', 'text')
    inlines = [ChoiceInline, TestCaseInline]
    fieldsets = (
        (None, {
            'fields': ('quiz', 'title', 'text', 'question_type', 'data_file')
        }),
        ('Для свободных ответов', {
            'fields': ('correct_text_answer',),
            'description': 'Заполнять только если выбран тип вопроса "Свободный ответ"'
        }),
    )

class QuestionInline(admin.TabularInline):
    model = Question
    fields = ('title', 'text', 'question_type', 'data_file')
    extra = 1

class QuizAssignmentInline(admin.TabularInline):
    model = QuizAssignment
    extra = 0
    autocomplete_fields = ['user', 'group']

    def get_readonly_fields(self, request, obj=None):
        return []

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'user':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            kwargs['queryset'] = User.objects.order_by('last_name', 'first_name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class QuizAdmin(admin.ModelAdmin):
    inlines = [QuestionInline, QuizAssignmentInline]
    search_fields = ['title']
    change_form_template = 'admin/quizzes/quiz/change_form.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:quiz_id>/bulk-assign/',
                 self.admin_site.admin_view(self.bulk_assign_view),
                 name='quizzes_quiz_bulk_assign'),
        ]
        return custom_urls + urls

    def bulk_assign_view(self, request, quiz_id):
        quiz = self.get_object(request, quiz_id)
        if quiz is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, str(quiz_id))

        if request.method == 'POST':
            form = BulkQuizAssignmentForm(request.POST)
            if form.is_valid():
                users = form.cleaned_data['users']
                start_date = form.cleaned_data['start_date']
                end_date = form.cleaned_data['end_date']
                max_attempts = form.cleaned_data['max_attempts']
                created = 0
                for user in users:
                    _, is_new = QuizAssignment.objects.get_or_create(
                        quiz=quiz,
                        user=user,
                        defaults={
                            'start_date': start_date,
                            'end_date': end_date,
                            'max_attempts': max_attempts,
                        }
                    )
                    if is_new:
                        created += 1
                self.message_user(request, f"Назначено {created} ученикам (пропущено дублей: {len(users) - created})")
                return HttpResponseRedirect(
                    reverse('admin:quizzes_quiz_change', args=[quiz_id])
                )
        else:
            form = BulkQuizAssignmentForm()

        context = {
            **self.admin_site.each_context(request),
            'form': form,
            'quiz': quiz,
            'opts': self.model._meta,
            'title': f'Массовое назначение: {quiz.title}',
        }
        return TemplateResponse(request, 'admin/quizzes/quiz/bulk_assign.html', context)

class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    readonly_fields = ('question', 'selected_choice', 'text_answer', 'code_answer', 'error_log', 'is_correct')
    can_delete = False
    extra = 0

class UserResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'quiz', 'score', 'date_completed', 'duration')
    list_filter = ('quiz', 'date_completed', 'user')
    search_fields = ('user__last_name', 'user__first_name', 'user__username', 'quiz__title')
    inlines = [UserAnswerInline]

class QuizAssignmentAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'group', 'get_user_display', 'start_date', 'end_date', 'max_attempts')
    list_filter = ('quiz', 'group')
    search_fields = ('quiz__title', 'user__last_name', 'user__first_name', 'user__username', 'group__name')
    autocomplete_fields = ['user', 'group', 'quiz']

    @admin.display(description='Ученик')
    def get_user_display(self, obj):
        if obj.user:
            full = f"{obj.user.last_name} {obj.user.first_name}".strip()
            return full if full else obj.user.username
        return '-'

class HelpCommentInline(admin.TabularInline):
    model = HelpComment
    readonly_fields = ('author', 'text', 'line_number', 'created_at')
    extra = 0
    can_delete = False

class HelpRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'question', 'quiz', 'status', 'has_unread_for_teacher', 'created_at', 'updated_at')
    list_filter = ('status', 'has_unread_for_teacher', 'quiz')
    search_fields = ('student__username', 'student__last_name', 'question__text')
    inlines = [HelpCommentInline]

admin.site.register(Quiz, QuizAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(UserResult, UserResultAdmin)
admin.site.register(QuizAssignment, QuizAssignmentAdmin)
admin.site.register(HelpRequest, HelpRequestAdmin)