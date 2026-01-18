from django.contrib import admin
from .models import Quiz, Question, Choice, UserResult, UserAnswer, TestCase, QuizAssignment

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4

class TestCaseInline(admin.StackedInline):
    model = TestCase
    extra = 1

class QuestionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'quiz', 'question_type') # Используем __str__ для обрезанного текста
    list_filter = ('quiz', 'question_type')
    inlines = [ChoiceInline, TestCaseInline]
    fieldsets = (
        (None, {
            'fields': ('quiz', 'text', 'question_type', 'data_file')
        }),
        ('Для свободных ответов', {
            'fields': ('correct_text_answer',),
            'description': 'Заполнять только если выбран тип вопроса "Свободный ответ"'
        }),
    )

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1

class QuizAssignmentInline(admin.TabularInline):
    model = QuizAssignment
    extra = 1
    autocomplete_fields = ['user', 'group']

class QuizAdmin(admin.ModelAdmin):
    inlines = [QuestionInline, QuizAssignmentInline]
    search_fields = ['title']

class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    readonly_fields = ('question', 'selected_choice', 'text_answer', 'code_answer', 'error_log', 'is_correct')
    can_delete = False
    extra = 0

class UserResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'quiz', 'score', 'date_completed', 'duration')
    list_filter = ('quiz', 'date_completed', 'user')
    search_fields = ('user__username', 'quiz__title')
    inlines = [UserAnswerInline]

class QuizAssignmentAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'group', 'user', 'start_date', 'end_date', 'max_attempts')
    list_filter = ('quiz', 'group')
    search_fields = ('quiz__title', 'user__username', 'group__name')
    autocomplete_fields = ['user', 'group', 'quiz']

admin.site.register(Quiz, QuizAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(UserResult, UserResultAdmin)
admin.site.register(QuizAssignment, QuizAssignmentAdmin)