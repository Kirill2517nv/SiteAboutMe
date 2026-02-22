import os
import shutil

from django.conf import settings
from django.db import migrations


def move_files_forward(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    QuestionImage = apps.get_model('quizzes', 'QuestionImage')
    QuestionFile = apps.get_model('quizzes', 'QuestionFile')
    media_root = settings.MEDIA_ROOT

    for quiz in Quiz.objects.filter(quiz_type='exam', slug__isnull=False):
        slug = quiz.slug

        for img in QuestionImage.objects.filter(question__quiz=quiz):
            old_rel = img.image.name if img.image else ''
            if not old_rel or old_rel.startswith(f'ege/{slug}/'):
                continue
            filename = os.path.basename(old_rel)
            new_rel = f'ege/{slug}/images/{filename}'
            old_abs = os.path.join(media_root, old_rel)
            new_abs = os.path.join(media_root, new_rel)
            if os.path.exists(old_abs):
                os.makedirs(os.path.dirname(new_abs), exist_ok=True)
                shutil.move(old_abs, new_abs)
            img.image = new_rel
            img.save(update_fields=['image'])

        for qf in QuestionFile.objects.filter(question__quiz=quiz):
            old_rel = qf.file.name if qf.file else ''
            if not old_rel or old_rel.startswith(f'ege/{slug}/'):
                continue
            filename = os.path.basename(old_rel)
            new_rel = f'ege/{slug}/files/{filename}'
            old_abs = os.path.join(media_root, old_rel)
            new_abs = os.path.join(media_root, new_rel)
            if os.path.exists(old_abs):
                os.makedirs(os.path.dirname(new_abs), exist_ok=True)
                shutil.move(old_abs, new_abs)
            qf.file = new_rel
            qf.save(update_fields=['file'])


def move_files_backward(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    QuestionImage = apps.get_model('quizzes', 'QuestionImage')
    QuestionFile = apps.get_model('quizzes', 'QuestionFile')
    media_root = settings.MEDIA_ROOT

    for quiz in Quiz.objects.filter(quiz_type='exam', slug__isnull=False):
        slug = quiz.slug

        for img in QuestionImage.objects.filter(question__quiz=quiz):
            old_rel = img.image.name if img.image else ''
            if not old_rel or not old_rel.startswith(f'ege/{slug}/images/'):
                continue
            filename = os.path.basename(old_rel)
            new_rel = f'question_images/{filename}'
            old_abs = os.path.join(media_root, old_rel)
            new_abs = os.path.join(media_root, new_rel)
            if os.path.exists(old_abs):
                os.makedirs(os.path.dirname(new_abs), exist_ok=True)
                shutil.move(old_abs, new_abs)
            img.image = new_rel
            img.save(update_fields=['image'])

        for qf in QuestionFile.objects.filter(question__quiz=quiz):
            old_rel = qf.file.name if qf.file else ''
            if not old_rel or not old_rel.startswith(f'ege/{slug}/files/'):
                continue
            filename = os.path.basename(old_rel)
            new_rel = f'question_files/{filename}'
            old_abs = os.path.join(media_root, old_rel)
            new_abs = os.path.join(media_root, new_rel)
            if os.path.exists(old_abs):
                os.makedirs(os.path.dirname(new_abs), exist_ok=True)
                shutil.move(old_abs, new_abs)
            qf.file = new_rel
            qf.save(update_fields=['file'])


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0029_populate_quiz_slugs'),
    ]

    operations = [
        migrations.RunPython(move_files_forward, move_files_backward),
    ]
