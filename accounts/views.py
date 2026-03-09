from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Max, Count, Q
from datetime import timedelta
from quizzes.models import (
    UserResult, UserAnswer, Quiz,
    ExamTaskProgress, HelpRequest, SolutionLike,
)


class ProfileView(LoginRequiredMixin, generic.TemplateView):
    template_name = 'registration/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        profile = getattr(user, 'profile', None)
        group = profile.group if profile else None

        # === Базовая статистика ===
        results = UserResult.objects.filter(user=user)
        total_attempts = results.count()
        unique_quizzes = results.values('quiz').distinct().count()

        answers = UserAnswer.objects.filter(user_result__user=user)
        total_answers = answers.values('question').distinct().count()
        correct_answers = answers.filter(is_correct=True).values('question').distinct().count()

        # Суммарное время
        total_time = results.aggregate(t=Sum('duration'))['t']

        # === Статистика по типам вопросов (уникальные вопросы) ===
        type_stats_qs = (
            answers
            .values('question__question_type')
            .annotate(
                total=Count('question', distinct=True),
                correct=Count('question', distinct=True, filter=Q(is_correct=True)),
            )
        )
        type_stats = {}
        for row in type_stats_qs:
            qtype = row['question__question_type']
            total = row['total']
            correct = row['correct']
            pct = round(correct / total * 100) if total > 0 else 0
            type_stats[qtype] = {'total': total, 'correct': correct, 'pct': pct}

        # === Статистика по тестам (лучший результат на каждый квиз) ===
        quiz_stats = list(
            results
            .values('quiz__id', 'quiz__title')
            .annotate(
                best_score=Max('score'),
                attempts=Count('id'),
            )
            .order_by('-best_score')
        )
        # Добавляем total вопросов для каждого квиза
        quiz_ids = [qs['quiz__id'] for qs in quiz_stats]
        quiz_totals = dict(
            Quiz.objects.filter(id__in=quiz_ids)
            .annotate(q_count=Count('questions'))
            .values_list('id', 'q_count')
        )
        for qs in quiz_stats:
            total_q = quiz_totals.get(qs['quiz__id'], 0)
            qs['total'] = total_q
            qs['pct'] = round(qs['best_score'] / total_q * 100) if total_q > 0 else 0

        # === ЕГЭ прогресс ===
        is_ege = profile.is_ege if profile else False
        ege_stats = {}
        if is_ege:
            ege_qs = ExamTaskProgress.objects.filter(user=user)
            ege_agg = ege_qs.aggregate(
                total=Count('id'),
                solved=Count('id', filter=Q(is_solved=True)),
                time_sec=Sum('time_spent_seconds'),
            )
            ege_stats = {
                'total': ege_agg['total'] or 0,
                'solved': ege_agg['solved'] or 0,
                'time': timedelta(seconds=ege_agg['time_sec'] or 0),
                'pct': round(ege_agg['solved'] / ege_agg['total'] * 100) if ege_agg['total'] else 0,
            }

        # === Последние результаты ===
        # annotate max_score через Count чтобы избежать N+1 запросов
        recent_results = list(
            results
            .select_related('quiz')
            .annotate(max_score=Count('quiz__questions', distinct=True))
            .order_by('-date_completed')[:5]
        )

        # === Помощь ===
        help_qs = HelpRequest.objects.filter(student=user)
        help_total = help_qs.count()
        help_resolved = help_qs.filter(status='resolved').count() if help_total else 0

        # === Лайки ===
        likes_received = SolutionLike.objects.filter(
            answer__user_result__user=user
        ).count()

        context.update({
            'profile_user': user,
            'group': group,
            'profile': profile,
            'total_attempts': total_attempts,
            'unique_quizzes': unique_quizzes,
            'total_answers': total_answers,
            'correct_answers': correct_answers,
            'total_time': total_time,
            'type_stats': type_stats,
            'quiz_stats': quiz_stats,
            'is_ege': is_ege,
            'ege_stats': ege_stats,
            'recent_results': recent_results,
            'help_total': help_total,
            'help_resolved': help_resolved,
            'likes_received': likes_received,
        })

        return context
