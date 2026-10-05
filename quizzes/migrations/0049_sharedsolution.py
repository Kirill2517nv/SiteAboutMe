import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import quizzes.models


class Migration(migrations.Migration):
    """Шаг 1 из 3: новая модель и временно пустой FK лайка на неё."""

    dependencies = [
        ('quizzes', '0048_codesubmission_language'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SharedSolution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name_visibility', models.CharField(
                    blank=True, default='', max_length=5, verbose_name='Имя под этим решением',
                    choices=[('', 'Как в профиле'), ('anon', 'Никому – подписывать «Ученик №…»'),
                             ('class', 'Только моему классу'), ('all', 'Всем')],
                )),
                ('comment', models.TextField(blank=True, default='', verbose_name='Разбор')),
                ('file', models.FileField(blank=True, null=True, upload_to=quizzes.models.solution_file_upload_path, verbose_name='Файл')),
                ('image', models.ImageField(blank=True, null=True, upload_to=quizzes.models.solution_image_upload_path, verbose_name='Изображение')),
                ('hidden', models.BooleanField(default=False, help_text='Решение не показывается ученикам (списано, не по делу).', verbose_name='Скрыто учителем')),
                ('notes_hidden', models.BooleanField(default=False, help_text='Код виден, комментарий, картинка и файл – нет.', verbose_name='Разбор скрыт учителем')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shared_solutions', to='quizzes.question', verbose_name='Задача')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shared_solutions', to=settings.AUTH_USER_MODEL, verbose_name='Автор')),
            ],
            options={
                'verbose_name': 'Решение в галерее',
                'verbose_name_plural': 'Решения в галерее',
                'constraints': [models.UniqueConstraint(fields=('user', 'question'), name='unique_shared_solution')],
            },
        ),
        migrations.AddField(
            model_name='solutionlike',
            name='solution',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='likes', to='quizzes.sharedsolution', verbose_name='Решение'),
        ),
        # related_name='likes' теперь у solution – старому полю нужно другое имя
        migrations.AlterField(
            model_name='solutionlike',
            name='answer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='quizzes.useranswer', verbose_name='Ответ'),
        ),
    ]
