from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Profile, StudentGroup

class StudentSignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True, label="Имя")
    last_name = forms.CharField(max_length=30, required=True, label="Фамилия")
    group = forms.ModelChoiceField(queryset=StudentGroup.objects.all(), required=True, label="Группа (Класс)", empty_label="Выберите группу")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
            # Создаем профиль и привязываем группу
            group = self.cleaned_data['group']
            Profile.objects.create(user=user, group=group)
        return user
