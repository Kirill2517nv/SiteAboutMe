"""Проверка статей учебника после наполнения: математика, ссылки, порядок блоков.

Запуск: python manage.py check_articles [--track spetskurs] [--prefix ballistics-]

Зачем отдельная команда, а не тест: проверять надо **содержимое базы**, а
тесты идут на пустой тестовой базе. Прогонять после каждой seed-команды.

Что ловится:

* **markdown съедает LaTeX.** Пара подчёркиваний-индексов в одном абзаце
  (`\\vec{a}_1 ... R_{12}`) для markdown выглядит как выделение курсивом, и
  внутрь формулы попадает <em>. MathJax получает испорченную строку и рисует
  мусор. В seed-файле глазами это не видно – только в отрисованном HTML.
  Лечится выносом формулы в блок block_type='formula': он идёт мимо
  markdownify;
* **кириллица внутри $...$** – TeX ломается на ней, а `\\text{}` спасает не
  всегда: проще писать латиницей, а слова выносить в текст;
* **битые перекрёстные ссылки** на статьи, которых нет;
* **разъехавшийся order блоков** – два блока с одним номером выводятся в
  случайном порядке.

Длинное тире здесь не проверяется: для него есть fix_dashes --dry-run.
"""
import re

from django.core.management.base import BaseCommand

from textbook.models import Article
from textbook.templatetags.textbook_tags import markdownify

CYRILLIC = re.compile('[А-Яа-яЁё]')
MATH = re.compile(r'\$\$(.+?)\$\$|\$([^$\n]+?)\$', re.S)
LINK = re.compile(r'\]\(/textbook/article/([a-z0-9-]+)/\)')
LATEX_CMD = re.compile(r'\\[a-zA-Z]+')


def _without_code(text):
    """Убрать блоки кода: доллар внутри них ничего не значит."""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    return re.sub(r'`[^`]*`', '', text)


class Command(BaseCommand):
    help = 'Проверяет статьи учебника: формулы, ссылки, порядок блоков'

    def add_arguments(self, parser):
        parser.add_argument('--track', help='Ограничить одной вкладкой (material/ege/spetskurs)')
        parser.add_argument('--prefix', help='Ограничить статьями, слаг которых начинается с этого')

    def handle(self, *args, **options):
        articles = Article.objects.all()
        if options.get('track'):
            articles = articles.filter(track=options['track'])
        if options.get('prefix'):
            articles = articles.filter(slug__startswith=options['prefix'])

        known = set(Article.objects.values_list('slug', flat=True))
        problems = 0

        for article in articles.order_by('track', 'order'):
            blocks = list(article.blocks.order_by('order'))

            # Дырки в нумерации безвредны – они остаются после удаления блока.
            # Опасны повторы: два блока с одним order выводятся в том порядке,
            # в каком их вернёт база, то есть как повезёт.
            orders = [b.order for b in blocks]
            if len(orders) != len(set(orders)):
                dupes = sorted({o for o in orders if orders.count(o) > 1})
                problems += 1
                self.stdout.write(self.style.ERROR(
                    f'{article.slug}: повторяющийся order блоков – {dupes}'))

            for block in blocks:
                for slug in LINK.findall(block.content):
                    if slug not in known:
                        problems += 1
                        self.stdout.write(self.style.ERROR(
                            f'{article.slug} #{block.order}: ссылка на несуществующую '
                            f'статью {slug}'))

                if block.block_type == 'formula':
                    if CYRILLIC.search(block.content):
                        problems += 1
                        self.stdout.write(self.style.ERROR(
                            f'{article.slug} #{block.order}: кириллица в формуле'))
                    continue
                if block.block_type != 'text':
                    continue

                source = _without_code(block.content)
                for match in MATH.finditer(source):
                    formula = match.group(1) or match.group(2)
                    if CYRILLIC.search(formula):
                        problems += 1
                        self.stdout.write(self.style.ERROR(
                            f'{article.slug} #{block.order}: кириллица в математике – '
                            f'{formula[:60]}'))

                html = str(markdownify(block.content))
                for match in MATH.finditer(html):
                    formula = match.group(1) or match.group(2)
                    if '<' in formula:
                        problems += 1
                        self.stdout.write(self.style.ERROR(
                            f'{article.slug} #{block.order}: markdown влез в формулу – '
                            f'{formula[:70]}'))
                if source.count('$') % 2:
                    problems += 1
                    self.stdout.write(self.style.ERROR(
                        f'{article.slug} #{block.order}: нечётное число $'))
                lost = [c for c in set(LATEX_CMD.findall(source)) if c not in html]
                if lost:
                    problems += 1
                    self.stdout.write(self.style.ERROR(
                        f'{article.slug} #{block.order}: команды LaTeX не дожили до '
                        f'HTML – {lost}'))

        count = articles.count()
        if problems:
            self.stdout.write(self.style.ERROR(
                f'Проверено {count} статей, проблем: {problems}'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Проверено {count} статей, проблем нет'))
