from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class BulkQuizAssignmentForm(forms.Form):
    """Форма для массового назначения теста нескольким ученикам."""
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Ученики",
        required=True,
    )
    start_date = forms.DateTimeField(
        required=False,
        label="Начало доступа",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text="Переопределяет глобальную дату начала",
    )
    end_date = forms.DateTimeField(
        required=False,
        label="Конец доступа",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text="Переопределяет глобальную дату конца",
    )
    max_attempts = forms.IntegerField(
        required=False,
        label="Максимум попыток",
        help_text="Переопределяет глобальное кол-во попыток",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['users'].queryset = User.objects.order_by('last_name', 'first_name')
        self.fields['users'].label_from_instance = self._label_from_instance

    @staticmethod
    def _label_from_instance(user):
        full_name = f"{user.last_name} {user.first_name}".strip()
        return full_name if full_name else user.username
