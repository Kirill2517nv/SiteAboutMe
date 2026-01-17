import os
import django
from django.core.management import call_command

# Настраиваем окружение Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

print("Начинаю выгрузку данных...")
# Открываем файл с правильной кодировкой
with open('data.json', 'w', encoding='utf-8') as f:
    # Вызываем dumpdata и направляем вывод прямо в файл
    call_command('dumpdata', exclude=['auth.permission', 'contenttypes'], stdout=f)

print("Готово! Данные сохранены в data.json")
