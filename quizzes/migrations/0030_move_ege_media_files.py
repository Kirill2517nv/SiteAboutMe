import os
import shutil
import sys

from django.conf import settings
from django.db import migrations


def _move_and_update(obj, field_name, old_rel, new_rel, media_root):
    """Перемещает файл и обновляет БД. Возвращает True если обновлено."""
    old_abs = os.path.join(media_root, old_rel)
    new_abs = os.path.join(media_root, new_rel)
    if os.path.exists(old_abs):
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        shutil.move(old_abs, new_abs)
        setattr(obj, field_name, new_rel)
        obj.save(update_fields=[field_name])
        return True
    else:
        sys.stderr.write(
            f'  WARNING: файл не найден на диске: {old_abs}, '
            f'путь в БД не изменён ({old_rel})\n'
        )
        return False


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
            _move_and_update(img, 'image', old_rel, new_rel, media_root)

        for qf in QuestionFile.objects.filter(question__quiz=quiz):
            old_rel = qf.file.name if qf.file else ''
            if not old_rel or old_rel.startswith(f'ege/{slug}/'):
                continue
            filename = os.path.basename(old_rel)
            new_rel = f'ege/{slug}/files/{filename}'
            _move_and_update(qf, 'file', old_rel, new_rel, media_root)


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
            _move_and_update(img, 'image', old_rel, new_rel, media_root)

        for qf in QuestionFile.objects.filter(question__quiz=quiz):
            old_rel = qf.file.name if qf.file else ''
            if not old_rel or not old_rel.startswith(f'ege/{slug}/files/'):
                continue
            filename = os.path.basename(old_rel)
            new_rel = f'question_files/{filename}'
            _move_and_update(qf, 'file', old_rel, new_rel, media_root)


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0029_populate_quiz_slugs'),
    ]

    operations = [
        migrations.RunPython(move_files_forward, move_files_backward),
    ]
