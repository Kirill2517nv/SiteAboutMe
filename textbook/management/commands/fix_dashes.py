"""Заменяет длинное тире «—» на короткое «–» во всех текстовых полях БД.

В исходниках (шаблоны, seed-файлы) тире уже вычищено, но контент живёт в базе:
статьи учебника, вопросы тестов, страницы. Команда идемпотентна – гоняем её
после каждого деплоя, где мог приехать новый текст с «—».
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models
from django.db.models.functions import Replace

EM, EN = "—", "–"
# admin.LogEntry – журнал действий, а не текст сайта: там имя объекта на момент правки.
SKIP_MODELS = {"admin.LogEntry"}
# Пути и адреса тире не содержат, а портить их заменой не хочется.
SKIP_FIELDS = (models.EmailField, models.URLField, models.SlugField, models.FileField)
# То, что написал ученик, а не мы. Код трогать нельзя вдвойне: тире внутри строкового
# литерала – это вывод программы, и замена уронит перепроверку решения.
SKIP_PATHS = {
    "quizzes.CodeSubmission.code",
    "quizzes.CodeSubmission.error_log",
    "quizzes.UserAnswer.code_answer",
    "quizzes.UserAnswer.text_answer",
    "quizzes.UserAnswer.error_log",
}


class Command(BaseCommand):
    help = "Заменить «—» на «–» во всех CharField/TextField базы"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="только показать, что будет изменено")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        total = 0

        for model in apps.get_models():
            if model._meta.proxy or not model._meta.managed or model._meta.label in SKIP_MODELS:
                continue
            for field in model._meta.local_fields:
                if not isinstance(field, (models.CharField, models.TextField)):
                    continue
                if isinstance(field, SKIP_FIELDS):
                    continue
                if f"{model._meta.label}.{field.name}" in SKIP_PATHS:
                    continue

                qs = model._default_manager.filter(**{f"{field.name}__contains": EM})
                count = qs.count()
                if not count:
                    continue

                total += count
                self.stdout.write(f"{count:6d} строк  {model._meta.label}.{field.name}")
                if not dry:
                    qs.update(**{field.name: Replace(field.name, models.Value(EM), models.Value(EN))})

        verb = "Найдено" if dry else "Исправлено"
        self.stdout.write(self.style.SUCCESS(f"{verb}: {total} строк"))
