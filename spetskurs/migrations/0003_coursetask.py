"""Simulation → CourseTask, удаление TheoryPage/TheoryBlock.

Переименование написано руками: makemigrations спрашивает про переименование
модели интерактивно, а автоматический ответ «нет» удалил бы таблицу вместе с
данными и завёл новую.

TheoryPage/TheoryBlock удаляются: это была урезанная копия
textbook.Article/ArticleBlock (см. docstring textbook.ArticleBlock – «образец:
spetskurs.TheoryBlock»), теория спецкурса переезжает на модели учебника.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('spetskurs', '0002_simulation_html_path'),
    ]

    operations = [
        migrations.RenameModel(old_name='Simulation', new_name='CourseTask'),
        migrations.AlterModelOptions(
            name='coursetask',
            options={
                'ordering': ['semester', 'order'],
                'verbose_name': 'Задача спецкурса',
                'verbose_name_plural': 'Задачи спецкурса',
            },
        ),
        migrations.AlterField(
            model_name='coursetask',
            name='title',
            field=models.CharField(max_length=200, verbose_name='Название задачи'),
        ),
        migrations.AlterField(
            model_name='coursetask',
            name='thumbnail',
            field=models.ImageField(
                blank=True, null=True, upload_to='spetskurs/tasks/',
                verbose_name='Превью изображение',
            ),
        ),
        migrations.AlterField(
            model_name='coursetask',
            name='html_path',
            field=models.CharField(
                blank=True, max_length=300,
                help_text='Относительный путь в static/, например: spetskurs/wasm/Task_2.html',
                verbose_name='Путь к HTML-файлу симуляции',
            ),
        ),
        migrations.AddField(
            model_name='coursetask',
            name='number',
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                help_text='Показывается как «Задача 2». Пусто – номер не выводится',
                verbose_name='Номер задачи',
            ),
        ),
        migrations.AddField(
            model_name='coursetask',
            name='frame_width',
            field=models.PositiveSmallIntegerField(
                default=16, verbose_name='Пропорция кадра: ширина'),
        ),
        migrations.AddField(
            model_name='coursetask',
            name='frame_height',
            field=models.PositiveSmallIntegerField(
                default=10, verbose_name='Пропорция кадра: высота'),
        ),
        migrations.AddField(
            model_name='coursetask',
            name='code_url',
            field=models.URLField(
                blank=True, help_text='main.cpp этой задачи на GitHub',
                verbose_name='Ссылка на исходник',
            ),
        ),
        migrations.DeleteModel(name='TheoryBlock'),
        migrations.DeleteModel(name='TheoryPage'),
    ]
