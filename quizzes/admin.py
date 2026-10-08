from django.contrib import admin
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from .models import Quiz, Question, Choice, UserResult, UserAnswer, TestCase, QuizAssignment, QuestionImage, QuestionFile, ExamTaskProgress, SharedSolution, SolutionLike, CodeSubmission, PracticeSession, PracticeItem
from .forms import BulkQuizAssignmentForm


class QuizRoleFilter(admin.SimpleListFilter):
    """Чем тест служит на сайте. В списке «Тестов» 85 из 126 – самопроверки и
    практикумы учебника, и без этого фильтра контрольную среди них не найти.
    `prefix` – путь до теста от модели списка ('' у Quiz, 'quiz__' у моделей с FK на тест)."""

    title = 'роль теста'
    parameter_name = 'role'
    prefix = ''

    def lookups(self, request, model_admin):
        return (
            ('standard', 'Контрольная'),
            ('practicum', 'Практикум блока'),
            ('selfcheck', 'Самопроверка статьи'),
            ('bank', 'Банк ЕГЭ'),
            ('exam', 'Вариант ЕГЭ'),
            ('check', 'Срез ЕГЭ'),
        )

    def queryset(self, request, queryset):
        from textbook.models import Section
        p = self.prefix
        # У Section.practicum_quiz related_name='+', обратного пути нет – подзапрос
        practicum = {f'{p}id__in': Section.objects.exclude(practicum_quiz=None)
                     .values('practicum_quiz')}
        value = self.value()
        if value == 'practicum':
            return queryset.filter(**practicum)
        if value == 'selfcheck':
            return queryset.filter(**{f'{p}is_self_check': True}).exclude(**practicum)
        if value == 'standard':
            return queryset.filter(**{f'{p}quiz_type': 'standard',
                                      f'{p}is_self_check': False}).exclude(**practicum)
        if value in ('bank', 'exam', 'check'):
            return queryset.filter(**{f'{p}quiz_type': value})
        return queryset


class RelatedQuizRoleFilter(QuizRoleFilter):
    prefix = 'quiz__'

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4

class TestCaseInline(admin.StackedInline):
    model = TestCase
    extra = 1

class QuestionImageInline(admin.TabularInline):
    model = QuestionImage
    extra = 1

class QuestionFileInline(admin.TabularInline):
    model = QuestionFile
    extra = 1

class QuestionAdmin(admin.ModelAdmin):
    list_display = ('title', 'quiz', 'question_type', 'ege_number', 'difficulty',
                    'exam_only', 'classroom_only')
    # ege_number в фильтрах – чтобы при смене кодификатора можно было увидеть все
    # задачи снятой темы разом. Массовая переразметка – manage.py retag_ege.
    # Фильтра по самому тесту нет: их 126, сайдбар превращался в простыню.
    # Тест ищется поиском по названию.
    list_filter = (RelatedQuizRoleFilter, 'question_type', 'ege_number', 'difficulty',
                   'exam_only', 'classroom_only')
    list_editable = ('exam_only', 'classroom_only')
    list_select_related = ('quiz',)
    search_fields = ('title', 'text', 'external_id', 'quiz__title')
    inlines = [ChoiceInline, TestCaseInline, QuestionImageInline, QuestionFileInline]
    fieldsets = (
        (None, {
            'fields': ('quiz', 'title', 'text', 'question_type')
        }),
        ('Подсказка', {
            'fields': ('hint',),
            'description': 'Ученик не видит подсказку и не знает о её существовании, '
                           'пока она не откроется: три неудачные попытки, меньше трёх '
                           'дней до дедлайна блока или рубильник «Открыть подсказки блока».'
        }),
        ('Для свободных ответов', {
            'fields': ('correct_text_answer', 'alternative_answers'),
            'description': 'Заполнять только если выбран тип вопроса "Свободный ответ"'
        }),
        ('ЕГЭ', {
            'fields': ('ege_number', 'topic', 'points', 'difficulty', 'solve_rate',
                       'exam_only', 'classroom_only', 'external_id', 'source_url'),
            'classes': ('collapse',),
            'description': 'Поля для задач ЕГЭ. solve_rate пересчитывается командой '
                           'recalc_ege_difficulty и перебивает ручную сложность: '
                           'правьте её, только если хотите зафиксировать уровень до '
                           'накопления статистики. «Только для экзамена» – резерв: '
                           'задача исчезает из учебных тренировок и достаётся '
                           'ученику лишь в режиме «Экзамен». «Только для работы '
                           'в классе» – набор для урока: одинаковый у всех учеников, '
                           'в тренировки и в экзамен не попадает. Массово – '
                           'manage.py mark_exam_pool [--pool classroom].'
        }),
    )

class QuestionInline(admin.TabularInline):
    model = Question
    fields = ('title', 'text', 'question_type')
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
    list_display = ('title', 'quiz_type', 'is_public', 'slug')
    list_filter = (QuizRoleFilter, 'is_public')
    inlines = [QuestionInline, QuizAssignmentInline]
    search_fields = ['title']
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'max_attempts', 'start_date', 'end_date',
                       'is_self_check')
        }),
        ('ЕГЭ', {
            'fields': ('quiz_type', 'exam_mode', 'is_public', 'slug', 'check_minutes'),
            'classes': ('collapse',),
        }),
    )
    change_form_template = 'admin/quizzes/quiz/change_form.html'

    # Срез назначают на сайте (/ege/checks/<id>/): окно у каждого класса своё и
    # живёт только в назначении. Даты теста и инлайн назначений здесь были
    # вторым местом с теми же датами – их и путали.
    def _is_check(self, obj):
        return obj is not None and obj.quiz_type == 'check'

    def get_fieldsets(self, request, obj=None):
        if not self._is_check(obj):
            return self.fieldsets
        return ((None, {
            'fields': ('title', 'description', 'quiz_type', 'slug', 'check_page'),
        }),)

    def get_readonly_fields(self, request, obj=None):
        return ('check_page',) if self._is_check(obj) else ()

    def get_inlines(self, request, obj):
        return [QuestionInline] if self._is_check(obj) else self.inlines

    @admin.display(description='Назначение и отчёт')
    def check_page(self, obj):
        from django.utils.html import format_html
        url = reverse('ege:ege_check_report', args=[obj.id])
        return format_html('<a href="{}">Открыть страницу среза на сайте</a>', url)

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
    # Ученик и тест – через поиск: фильтры по ним были списками на сотню строк
    list_filter = (RelatedQuizRoleFilter, 'date_completed')
    list_select_related = ('user', 'quiz')
    search_fields = ('user__last_name', 'user__first_name', 'user__username', 'quiz__title')
    inlines = [UserAnswerInline]

class QuizAssignmentAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'group', 'get_user_display', 'start_date', 'end_date', 'max_attempts')
    list_filter = (('quiz', admin.RelatedOnlyFieldListFilter), 'group')
    list_select_related = ('quiz', 'group', 'user')
    search_fields = ('quiz__title', 'user__last_name', 'user__first_name', 'user__username', 'group__name')
    autocomplete_fields = ['user', 'group', 'quiz']

    @admin.display(description='Ученик')
    def get_user_display(self, obj):
        if obj.user:
            full = f"{obj.user.last_name} {obj.user.first_name}".strip()
            return full if full else obj.user.username
        return '-'

class ExamTaskProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'quiz', 'question', 'is_solved', 'attempts_to_solve', 'time_spent_seconds')
    list_filter = ('is_solved', ('quiz', admin.RelatedOnlyFieldListFilter))
    search_fields = ('user__last_name', 'user__first_name', 'user__username')
    list_select_related = ('user', 'quiz', 'question')
    readonly_fields = ('is_solved', 'first_solved_at')

admin.site.register(Quiz, QuizAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(UserResult, UserResultAdmin)
admin.site.register(QuizAssignment, QuizAssignmentAdmin)
class SharedSolutionAdmin(admin.ModelAdmin):
    list_display = ('user', 'question', 'name_visibility', 'hidden', 'notes_hidden',
                    'has_file', 'has_image', 'created_at')
    list_editable = ('hidden', 'notes_hidden')
    list_filter = ('hidden', 'notes_hidden', 'question__quiz__quiz_type')
    search_fields = ('user__last_name', 'user__first_name', 'user__username')
    list_select_related = ('user', 'question')
    raw_id_fields = ('user', 'question')
    readonly_fields = ('created_at',)

    @admin.display(boolean=True, description='Файл')
    def has_file(self, obj):
        return bool(obj.file)

    @admin.display(boolean=True, description='Картинка')
    def has_image(self, obj):
        return bool(obj.image)

class CodeSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'question', 'quiz', 'status', 'is_correct', 'cpu_time_ms', 'memory_kb', 'created_at')
    list_filter = ('status', 'is_correct', 'language', RelatedQuizRoleFilter)
    search_fields = ('user__last_name', 'user__first_name', 'user__username')
    list_select_related = ('user', 'quiz', 'question')
    readonly_fields = ('cpu_time_ms', 'memory_kb')

class SolutionLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'solution', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__last_name', 'user__first_name', 'user__username')
    readonly_fields = ('user', 'solution', 'created_at')

class PracticeItemInline(admin.TabularInline):
    model = PracticeItem
    fields = ('order', 'question', 'text_answer', 'is_correct', 'attempts', 'gave_up',
              'seconds', 'answered_at')
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    """Журнал тренировок: по нему считается вся аналитика ЕГЭ."""
    list_display = ('user', 'kind', 'ege_number', 'mode', 'solved_display', 'created_at', 'finished_at')
    list_filter = ('kind', 'mode', 'ege_number')
    search_fields = ('user__last_name', 'user__first_name', 'user__username')
    list_select_related = ('user',)
    readonly_fields = ('created_at',)
    inlines = [PracticeItemInline]

    def get_queryset(self, request):
        # Три счётчика одним запросом – раньше колонка читала задачи на каждую строку
        return super().get_queryset(request).annotate(
            _total=Count('items'),
            _answered=Count('items', filter=Q(items__answered_at__isnull=False)),
            _correct=Count('items', filter=Q(items__answered_at__isnull=False,
                                             items__is_correct=True)),
        )

    @admin.display(description='Решено')
    def solved_display(self, obj):
        return f'{obj._correct} / {obj._answered} из {obj._total}'


admin.site.register(ExamTaskProgress, ExamTaskProgressAdmin)
admin.site.register(SharedSolution, SharedSolutionAdmin)
admin.site.register(CodeSubmission, CodeSubmissionAdmin)
admin.site.register(SolutionLike, SolutionLikeAdmin)
# HintChoice в админке нет: журнал только для чтения, руками его не открывали.
