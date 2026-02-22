import re

from django.db import migrations


def populate_slugs(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    for quiz in Quiz.objects.filter(quiz_type='exam', slug__isnull=True):
        match = re.search(r'ID:\s*(\d+)', quiz.description or '')
        if match:
            slug = f'variant-{match.group(1)}'
        else:
            slug = f'ege-{quiz.pk}'
        quiz.slug = slug
        quiz.save(update_fields=['slug'])


def clear_slugs(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    Quiz.objects.filter(quiz_type='exam').update(slug=None)


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0028_quiz_slug_and_upload_paths'),
    ]

    operations = [
        migrations.RunPython(populate_slugs, clear_slugs),
    ]
