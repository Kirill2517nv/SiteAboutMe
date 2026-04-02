from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('spetskurs', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='simulation',
            name='wasm_path',
        ),
        migrations.RemoveField(
            model_name='simulation',
            name='js_path',
        ),
        migrations.AddField(
            model_name='simulation',
            name='html_path',
            field=models.CharField(
                blank=True,
                help_text='Относительный путь в static/, например: spetskurs/wasm/pendulum.html',
                max_length=300,
                verbose_name='Путь к HTML-файлу симуляции',
            ),
        ),
    ]
