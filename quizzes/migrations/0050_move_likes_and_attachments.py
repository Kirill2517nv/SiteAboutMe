from django.db import migrations


def forwards(apps, schema_editor):
    """
    Шаг 2 из 3: лайки и вложения вариантов переезжают на SharedSolution.

    Вложение было на (автор, вариант, задача), а задача принадлежит одному
    варианту – значит (автор, задача) однозначно, и файл переносится как есть
    (меняется только запись в базе, сам файл на диске не трогается).
    Лайк был на конкретный ответ; ответов у автора по задаче бывает несколько,
    и один зритель мог лайкнуть два из них – такой дубль схлопывается в один.
    Лайк самому себе старая вьюха не давала поставить, но если он есть – он
    удаляется: своё решение лайкать нельзя.
    """
    Attachment = apps.get_model('quizzes', 'SolutionAttachment')
    Shared = apps.get_model('quizzes', 'SharedSolution')
    Like = apps.get_model('quizzes', 'SolutionLike')

    for att in Attachment.objects.all():
        shared, _ = Shared.objects.get_or_create(user_id=att.user_id, question_id=att.question_id)
        shared.comment = att.comment
        shared.file = att.file.name or None
        shared.image = att.image.name or None
        shared.save()

    seen = set()
    for like in Like.objects.select_related('answer__user_result').order_by('created_at', 'id'):
        author_id = like.answer.user_result.user_id
        if author_id == like.user_id:
            like.delete()
            continue
        shared, _ = Shared.objects.get_or_create(user_id=author_id, question_id=like.answer.question_id)
        if (like.user_id, shared.id) in seen:
            like.delete()
            continue
        seen.add((like.user_id, shared.id))
        like.solution_id = shared.id
        like.save(update_fields=['solution'])


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0049_sharedsolution'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
