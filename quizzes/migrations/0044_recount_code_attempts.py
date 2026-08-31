"""
Пересчитываем попытки по задачам на код: до этого их не считал никто.

Счётчик `attempts_to_solve` отвечает на вопрос «с какой попытки ученик взял
задачу», поэтому считаем отправки кода до первой верной включительно; если
задача не решена – все отправки. Значения, накопленные проверками текстовых
ответов, не трогаем: там счётчик уже верный.
"""
from django.db import migrations


def recount(apps, schema_editor):
    ExamTaskProgress = apps.get_model('quizzes', 'ExamTaskProgress')
    CodeSubmission = apps.get_model('quizzes', 'CodeSubmission')

    updated = []
    for progress in ExamTaskProgress.objects.filter(
        question__question_type='code',
    ).select_related('question'):
        submissions = list(
            CodeSubmission.objects
            .filter(user_id=progress.user_id, quiz_id=progress.quiz_id,
                    question_id=progress.question_id)
            .order_by('created_at')
            .values_list('is_correct', flat=True)
        )
        if not submissions:
            continue
        attempts = len(submissions)
        for i, is_correct in enumerate(submissions, 1):
            if is_correct:
                attempts = i
                break
        if attempts != progress.attempts_to_solve:
            progress.attempts_to_solve = attempts
            updated.append(progress)

    ExamTaskProgress.objects.bulk_update(updated, ['attempts_to_solve'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0043_backfill_variant_attempts'),
    ]

    operations = [
        migrations.RunPython(recount, migrations.RunPython.noop),
    ]
