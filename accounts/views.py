from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from .forms import StudentSignUpForm
from quizzes.models import UserResult, UserAnswer


class SignUpView(generic.CreateView):
    form_class = StudentSignUpForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'


class ProfileView(LoginRequiredMixin, generic.TemplateView):
    template_name = 'registration/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Получаем профиль пользователя (группа)
        profile = getattr(user, 'profile', None)
        group = profile.group if profile else None
        
        # Статистика по тестам
        results = UserResult.objects.filter(user=user)
        total_attempts = results.count()
        unique_quizzes = results.values('quiz').distinct().count()
        
        # Статистика по ответам
        answers = UserAnswer.objects.filter(user_result__user=user)
        total_answers = answers.count()
        correct_answers = answers.filter(is_correct=True).count()
        
        # Процент правильных ответов
        success_rate = round((correct_answers / total_answers * 100), 1) if total_answers > 0 else 0
        
        context.update({
            'profile_user': user,
            'group': group,
            'total_attempts': total_attempts,
            'unique_quizzes': unique_quizzes,
            'total_answers': total_answers,
            'correct_answers': correct_answers,
            'success_rate': success_rate,
        })
        
        return context
