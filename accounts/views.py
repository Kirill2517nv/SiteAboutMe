from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.views import generic
from django import forms

from quizzes.models import ExamTaskProgress, HelpRequest, Question, Quiz, UserResult
from quizzes.views import EGE_RECOMMENDED_TIME, ege_time_color
from textbook.models import Article, ArticleProgress
from textbook.services import profile_textbook_stats

from .models import Profile


class AvatarForm(forms.ModelForm):
    """
    Загрузка аватара. Именно ModelForm, а не присваивание `request.FILES`
    напрямую: только форма прогоняет файл через Pillow и отсекает «картинку»,
    которая на деле картинкой не является.
    """
    class Meta:
        model = Profile
        fields = ['avatar']

    def clean_avatar(self):
        avatar = self.cleaned_data['avatar']
        if avatar and avatar.size > 2 * 1024 * 1024:
            raise forms.ValidationError('Файл больше 2 МБ — уменьшите картинку.')
        return avatar


def _ege_stats(user):
    """
    Сводка по ЕГЭ: тренажёр вариантов + теория ЕГЭ (вкладка учебника).

    Разбивка по номерам заданий 1–27 — единственная метрика, которая прямо
    показывает пробелы: `Question.topic` в базе почти не заполнен, а
    `ege_number` есть у каждой задачи варианта.
    """
    variant_ids = list(
        Quiz.objects.filter(quiz_type='exam', is_public=True).values_list('id', flat=True)
    )

    # {номер задания: [решено, всего]} — «всего» по опубликованным вариантам,
    # чтобы прочерк у нерешённых номеров отличался от «такого задания нет».
    by_number = {}
    for number, total in (
        Question.objects
        .filter(quiz_id__in=variant_ids, ege_number__isnull=False)
        .values_list('ege_number').annotate(n=Count('id')).order_by('ege_number')
    ):
        by_number[number] = {
            'number': number, 'solved': 0, 'total': total,
            'avg_seconds': 0, 'avg_mm_ss': '', 'color': '',
            # Ориентир показываем всегда, даже пока задача не решена: ученику
            # нужно знать, к какому времени стремиться, до первой попытки.
            'recommended_min': EGE_RECOMMENDED_TIME.get(number, 5),
        }

    progress = ExamTaskProgress.objects.filter(user=user, quiz_id__in=variant_ids)
    # Среднее время — только по решённым задачам с засечённым временем: нули от
    # задач, где таймер не сработал, занизили бы среднее и покрасили бы номер
    # зелёным на пустом месте.
    for row in (
        progress.filter(is_solved=True, question__ege_number__isnull=False)
        .values('question__ege_number')
        .annotate(
            n=Count('id'),
            t=Avg('time_spent_seconds', filter=Q(time_spent_seconds__gt=0)),
        )
    ):
        item = by_number.get(row['question__ege_number'])
        if item is None:
            continue
        item['solved'] = min(row['n'], item['total'])
        seconds = int(row['t'] or 0)
        minutes, secs = divmod(seconds, 60)
        item['avg_seconds'] = seconds
        item['avg_mm_ss'] = f'{minutes}:{secs:02d}' if seconds else ''
        item['color'] = ege_time_color(seconds, item['number'])

    agg = progress.aggregate(started=Count('id'), seconds=Sum('time_spent_seconds'))
    total_tasks = sum(item['total'] for item in by_number.values())
    solved_tasks = sum(item['solved'] for item in by_number.values())

    variants = list(
        Quiz.objects.filter(id__in=variant_ids)
        .annotate(
            num_questions=Count('questions', distinct=True),
            best_score=Max('userresult__score', filter=Q(userresult__user=user)),
            attempts=Count('userresult', distinct=True, filter=Q(userresult__user=user)),
        )
        .order_by('title')
    )
    # Время по варианту — отдельным запросом: ещё один JOIN в annotate выше
    # размножил бы строки и испортил Max/Count.
    spent_by_variant = dict(
        progress.values('quiz_id').annotate(t=Sum('time_spent_seconds'))
        .values_list('quiz_id', 't')
    )
    for variant in variants:
        variant.spent_seconds = spent_by_variant.get(variant.id) or 0

    # Теория ЕГЭ появится позже — блок сам покажется, когда статьи опубликуют.
    theory_total = Article.objects.filter(track='ege', is_published=True).count()
    theory_read = ArticleProgress.objects.filter(
        user=user, article__track='ege', article__is_published=True,
        status__in=('read', 'mastered'),
    ).count()

    return {
        'has_data': bool(agg['started'] or theory_total),
        'solved': solved_tasks,
        'total': total_tasks,
        'pct': round(solved_tasks / total_tasks * 100) if total_tasks else 0,
        'time': timedelta(seconds=agg['seconds'] or 0),
        'by_number': sorted(by_number.values(), key=lambda item: item['number']),
        'variants': variants,
        'theory_total': theory_total,
        'theory_read': theory_read,
        'theory_pct': round(theory_read / theory_total * 100) if theory_total else 0,
    }


class ProfileView(LoginRequiredMixin, generic.TemplateView):
    template_name = 'registration/profile.html'

    def get_profile_user(self):
        """
        Чей профиль показываем. Чужой доступен только суперпользователю —
        тот же критерий «учителя», что и у отчётов по блокам учебника.
        """
        user_id = self.kwargs.get('user_id')
        if user_id is None or user_id == self.request.user.id:
            return self.request.user
        if not self.request.user.is_superuser:
            raise PermissionDenied
        return get_object_or_404(User, id=user_id)

    def post(self, request, *args, **kwargs):
        """Смена аватара. Только в своём профиле: учитель чужой не трогает."""
        if self.get_profile_user() != request.user:
            raise PermissionDenied
        profile, _ = Profile.objects.get_or_create(user=request.user)
        old_avatar = profile.avatar.name
        form = AvatarForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            # Django файлы при замене не удаляет (откат транзакции оставил бы битую
            # ссылку), поэтому чистим сами — уже после успешного save().
            if old_avatar and old_avatar != profile.avatar.name:
                profile.avatar.storage.delete(old_avatar)
            return redirect('accounts:profile')
        return self.render_to_response(self.get_context_data(
            avatar_error=form.errors.get('avatar', ['Не удалось загрузить файл'])[0]
        ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_profile_user()
        is_own = user == self.request.user

        profile = getattr(user, 'profile', None)
        help_qs = HelpRequest.objects.filter(student=user)

        context.update({
            'profile_user': user,
            'profile': profile,
            'group': profile.group if profile else None,
            'is_own': is_own,
            'is_ege': profile.is_ege if profile else False,
            'textbook': profile_textbook_stats(user),
            'ege': _ege_stats(user),
            'help_open': help_qs.exclude(status='resolved').count(),
            'help_unread': help_qs.filter(has_unread_for_student=True).count(),
            'recent_results': list(
                UserResult.objects.filter(user=user).select_related('quiz')
                .annotate(max_score=Count('quiz__questions', distinct=True))
                .order_by('-date_completed')[:5]
            ),
        })

        # Учителю — переключение между учениками прямо из профиля.
        if self.request.user.is_superuser:
            context['students'] = (
                User.objects.filter(is_superuser=False)
                .select_related('profile__group')
                .order_by('profile__group__name', 'last_name', 'username')
            )

        return context
