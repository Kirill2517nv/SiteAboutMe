from django.db import migrations, models


def fill_kind(apps, schema_editor):
    # До раздела уведомления различала только ссылка: правки ведут в учебник.
    Notification = apps.get_model('accounts', 'Notification')
    Notification.objects.filter(url__startswith='/textbook/').update(kind='suggestion')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='kind',
            field=models.CharField(choices=[('suggestion', 'Ваши правки к статьям'), ('solution', 'Ваши комментарии к задачам')], default='solution', max_length=20, verbose_name='Раздел'),
            preserve_default=False,
        ),
        migrations.RunPython(fill_kind, migrations.RunPython.noop),
    ]
