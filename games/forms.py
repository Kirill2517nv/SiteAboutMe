from django import forms
from django.forms import modelformset_factory
from .models import Category, Question, QuestionMedia, GamePack


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['title', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['text', 'answer', 'points', 'order']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
            'answer': forms.TextInput(attrs={'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
            'points': forms.NumberInput(attrs={'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white', 'min': '1'}),
            'order': forms.HiddenInput(),
        }


QuestionFormSet = modelformset_factory(
    Question,
    form=QuestionForm,
    min_num=1,
    max_num=20,
    extra=4,
    can_delete=False,
)


class QuestionMediaForm(forms.ModelForm):
    class Meta:
        model = QuestionMedia
        fields = ['media_type', 'file', 'order']

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data


class QuestionEditForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['text', 'answer', 'points']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
            'answer': forms.TextInput(attrs={'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
            'points': forms.NumberInput(attrs={'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white', 'min': '1'}),
        }


class CategoryModerationForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['status', 'moderator_comment']
        widgets = {
            'moderator_comment': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
        }


class GamePackForm(forms.ModelForm):
    class Meta:
        model = GamePack
        fields = ['title', 'description', 'is_public']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-white'}),
        }
