from django.db import migrations


def migrate_files_forward(apps, schema_editor):
    """Copy Lesson.file paths to LessonAttachment rows."""
    Lesson = apps.get_model('lessons', 'Lesson')
    LessonAttachment = apps.get_model('lessons', 'LessonAttachment')
    for lesson in Lesson.objects.exclude(file='').exclude(file__isnull=True):
        LessonAttachment.objects.create(
            lesson=lesson,
            file=lesson.file,
            title='',
            order=0,
        )


def migrate_files_backward(apps, schema_editor):
    """Copy first attachment back to Lesson.file."""
    Lesson = apps.get_model('lessons', 'Lesson')
    LessonAttachment = apps.get_model('lessons', 'LessonAttachment')
    for attachment in LessonAttachment.objects.order_by('lesson_id', 'order'):
        Lesson.objects.filter(pk=attachment.lesson_id, file='').update(file=attachment.file)


class Migration(migrations.Migration):

    dependencies = [
        ('lessons', '0010_add_lesson_attachment_and_presentation_fields'),
    ]

    operations = [
        migrations.RunPython(migrate_files_forward, migrate_files_backward),
    ]
