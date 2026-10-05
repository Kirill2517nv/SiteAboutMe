from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_studentgroup_in_stats'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='solution_name_visibility',
            field=models.CharField(
                choices=[('anon', 'Никому – подписывать «Ученик №…»'), ('class', 'Только моему классу'), ('all', 'Всем')],
                default='anon', max_length=5, verbose_name='Имя под решениями',
            ),
        ),
    ]
