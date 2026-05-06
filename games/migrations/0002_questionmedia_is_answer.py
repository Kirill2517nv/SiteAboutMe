from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='questionmedia',
            name='is_answer',
            field=models.BooleanField(default=False, verbose_name='Медиа к ответу'),
        ),
        migrations.AlterModelOptions(
            name='questionmedia',
            options={
                'ordering': ['is_answer', 'media_type', 'order'],
                'verbose_name': 'Медиафайл вопроса',
                'verbose_name_plural': 'Медиафайлы вопросов',
            },
        ),
    ]
