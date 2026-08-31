"""
Восстанавливаем попытки по вариантам: раньше их никто не считал.

`attempts_to_solve` увеличивался только при синхронной проверке текстового
ответа, а задачи на код туда не попадали вовсе – отправка кода шла другим
путём. В итоге у решённой задания 17 с пятью отправками стояло ноль попыток,
а статистика по вариантам фильтрует строки по `is_solved OR attempts > 0` и
считала точность по одним только решённым задачам.

Восстанавливаем по тому, что сохранилось:
  * задачи на код – по числу отправок (CodeSubmission);
  * остальные – одна попытка на факт непустого ответа в законченном варианте.

Строки, заведённые одним лишь таймером (задачу открыли, но не отвечали),
остаются с нулём – открыть задачу не значит попытаться её решить.
"""
from django.db import migrations
from django.db.models import Count


def backfill(apps, schema_editor):
    ExamTaskProgress = apps.get_model('quizzes', 'ExamTaskProgress')
    CodeSubmission = apps.get_model('quizzes', 'CodeSubmission')
    UserAnswer = apps.get_model('quizzes', 'UserAnswer')

    submissions = {
        (row['user_id'], row['quiz_id'], row['question_id']): row['n']
        for row in CodeSubmission.objects
        .filter(quiz__quiz_type='exam')
        .values('user_id', 'quiz_id', 'question_id')
        .annotate(n=Count('id'))
    }

    answered = set(
        UserAnswer.objects
        .filter(user_result__quiz__quiz_type='exam')
        .exclude(text_answer='', code_answer='', selected_choice__isnull=True)
        .values_list('user_result__user_id', 'user_result__quiz_id', 'question_id')
    )

    updated = []
    for progress in ExamTaskProgress.objects.filter(attempts_to_solve=0):
        key = (progress.user_id, progress.quiz_id, progress.question_id)
        attempts = submissions.get(key) or (1 if key in answered or progress.is_solved else 0)
        if attempts:
            progress.attempts_to_solve = attempts
            updated.append(progress)

    ExamTaskProgress.objects.bulk_update(updated, ['attempts_to_solve'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0042_fix_partial_task_expected_output'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
