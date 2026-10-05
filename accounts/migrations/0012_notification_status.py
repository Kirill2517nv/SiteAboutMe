from django.db import migrations, models


def fill_status(apps, schema_editor):
    # До поля решение жило только в тексте уведомления.
    Notification = apps.get_model('accounts', 'Notification')
    Notification.objects.filter(text__contains='отклон').update(status='rejected')
    Notification.objects.filter(text__contains='принят').update(status='accepted')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_notification_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='status',
            field=models.CharField(choices=[('accepted', 'Принято'), ('rejected', 'Отклонено'), ('pending', 'На рассмотрении')], default='pending', max_length=20, verbose_name='Решение'),
        ),
        migrations.RunPython(fill_status, migrations.RunPython.noop),
    ]
