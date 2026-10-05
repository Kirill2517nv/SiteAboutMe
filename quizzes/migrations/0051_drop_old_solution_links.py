import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Шаг 3 из 3: старые связи больше не нужны – данные уже на SharedSolution."""

    dependencies = [
        ('quizzes', '0050_move_likes_and_attachments'),
    ]

    operations = [
        migrations.RemoveConstraint(model_name='solutionlike', name='unique_solution_like'),
        migrations.RemoveField(model_name='solutionlike', name='answer'),
        migrations.AlterField(
            model_name='solutionlike',
            name='solution',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='likes', to='quizzes.sharedsolution', verbose_name='Решение'),
        ),
        migrations.AddConstraint(
            model_name='solutionlike',
            constraint=models.UniqueConstraint(fields=('user', 'solution'), name='unique_solution_like_v2'),
        ),
        migrations.DeleteModel(name='SolutionAttachment'),
    ]
