from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.views import generic
from django import forms

from quizzes.models import UserResult
from textbook.services import profile_textbook_stats

from .models import Profile, StudentGroup


class AlumniForm(forms.ModelForm):
    """
    Карточку выпускника заполняет сам ученик – учитель её не редактирует.
    Поля рисуются в шаблоне вручную: Tailwind сканирует только templates/ и
    static/js/, классы из Python в собранный CSS не попадут.
    """
    class Meta:
        model = Profile
        fields = ['alumni_place', 'alumni_about']


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
            raise forms.ValidationError('Файл больше 2 МБ – уменьшите картинку.')
        return avatar


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
        """Аватар и карточка выпускника. Только в своём профиле: учитель чужой не трогает."""
        if self.get_profile_user() != request.user:
            raise PermissionDenied
        profile, _ = Profile.objects.get_or_create(user=request.user)

        # Формы на странице две, различаем по полю: у карточки нет файлов.
        if 'alumni_about' in request.POST:
            alumni_form = AlumniForm(request.POST, instance=profile)
            if alumni_form.is_valid():
                alumni_form.save()
            return redirect('accounts:profile')

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
        context.update({
            'profile_user': user,
            'profile': profile,
            'group': profile.group if profile else None,
            'is_own': is_own,
            'is_ege': profile.is_ege if profile else False,
            'textbook': profile_textbook_stats(user),
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


class AlumniView(generic.ListView):
    """
    Публичный архив: выпускные классы с общим фото, словом учителя и карточками.

    Открыт всем – в отличие от статистики учебника, где фамилии школьников
    наружу не отдаются: здесь класс публикует учитель, а текст о себе пишет
    сам выпускник.
    """
    template_name = 'accounts/alumni.html'
    context_object_name = 'groups'

    def get_queryset(self):
        groups = list(
            StudentGroup.objects
            .exclude(graduation_year=None)
            .prefetch_related(Prefetch('students', queryset=(
                Profile.objects.select_related('user')
                .order_by('user__first_name', 'user__last_name')
            )))
            .order_by('-graduation_year', 'name')
        )
        # Самый ранний выпуск – первый. Год не зашит в код: появится класс
        # старше, и «первым» станет он, без правок шаблона.
        if groups:
            first_year = groups[-1].graduation_year
            for group in groups:
                group.is_first = group.graduation_year == first_year
        return groups
