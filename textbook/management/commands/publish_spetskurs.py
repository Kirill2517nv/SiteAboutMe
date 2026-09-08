"""Выпуск разбора: снимает статьи задачи спецкурса с черновика.

Текст пишет `seed_spetskurs_<задача>`, и `is_published` стоит у него в
`create_defaults` – новая статья всегда рождается черновиком, чтобы повторный
прогон правил текст и не снимал с публикации уже выпущенное. Решение о выпуске
остаётся за учителем, и вот оно: вычитал статью на сайте (суперпользователю
черновик открыт по прямой ссылке) – выпустил.

Разборы выпускаются по одной статье, когда вычитаны, поэтому слаги статей –
позиционный аргумент; без них выходит весь разбор задачи разом.

    python manage.py publish_spetskurs ballistics
    python manage.py publish_spetskurs ballistics ballistics-1-fizika
"""
from django.core.management.base import BaseCommand, CommandError

from textbook.models import Article


class Command(BaseCommand):
    help = 'Публикует статьи разбора задачи спецкурса'

    def add_arguments(self, parser):
        parser.add_argument('task', help='slug задачи: ballistics, pendulum, …')
        parser.add_argument('articles', nargs='*',
                            help='slug статей; без них – весь разбор задачи')

    def handle(self, task, articles, **options):
        found = list(
            Article.objects
            .filter(track='spetskurs', course_task__slug=task)
            .filter(**({'slug__in': articles} if articles else {}))
            .order_by('order')
        )

        # Опечатка в слаге иначе неотличима от успеха: обновилось ноль строк,
        # а команда бодро отчиталась «готово», и разбора на сайте так и нет.
        missing = set(articles) - {a.slug for a in found}
        if missing:
            raise CommandError('Нет таких статей: ' + ', '.join(sorted(missing)))
        if not found:
            raise CommandError(
                f'У задачи «{task}» нет статей. Проверьте slug задачи '
                f'и прогоните seed_spetskurs_… – он создаёт черновики.'
            )

        Article.objects.filter(pk__in=[a.pk for a in found]).update(is_published=True)
        for article in found:
            self.stdout.write(f'  {article.slug} – {article.title}')
        self.stdout.write(self.style.SUCCESS(f'Выпущено статей: {len(found)}'))
