from django.contrib import admin
from .models import Quiz, Question, Choice, UserResult, UserAnswer, TestCase

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

class QuizAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]

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

admin.site.register(Quiz, QuizAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(UserResult, UserResultAdmin)
