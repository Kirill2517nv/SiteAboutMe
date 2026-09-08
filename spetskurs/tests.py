from io import StringIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from textbook.models import Article

from .models import CourseTask

# Боевое хранилище статики требует прогнанного collectstatic — тестам он не нужен.
NO_MANIFEST_STATIC = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})


@NO_MANIFEST_STATIC
class UnpublishedTaskArticlesTests(TestCase):
    """Задача есть в курсе, а разбор ещё не вычитан.

    Статьи задачи лежат снятыми с публикации, пока преподаватель их не прочитал.
    Страницы обязаны говорить об этом прямо: у задачи с невыпущенным разбором
    материалов ноль, а не столько, сколько строк лежит в базе.
    """

    @classmethod
    def setUpTestData(cls):
        cls.task = CourseTask.objects.create(
            slug='pendulum', title='Математический маятник', number=3,
            html_path='spetskurs/wasm/Task_2.html', is_published=True,
        )
        cls.draft = Article.objects.create(
            slug='pendulum-physics', title='Физика: уравнение маятника',
            track='spetskurs', course_task=cls.task, order=1, is_published=False,
        )
        cls.student = User.objects.create_user('pupil', password='pw')
        cls.teacher = User.objects.create_superuser('teacher', password='pw')

    def test_task_page_shows_placeholder_and_hides_draft(self):
        page = self.client.get(self.task.get_absolute_url()).content.decode()

        self.assertIn('Разбор задачи готовится', page)
        self.assertNotIn(self.draft.title, page)
        self.assertNotIn('Разбор задачи<', page, 'секция разбора при пустом списке')

    def test_card_counts_published_only(self):
        """Счётчик на карточке – главный источник вранья: обратная связь FK
        считает и черновики, и карточка обещала бы разбор, которого нет."""
        page = self.client.get(reverse('spetskurs:task_list')).content.decode()
        self.assertIn('разбор готовится', page)
        self.assertNotIn('1 материал', page)

        Article.objects.filter(pk=self.draft.pk).update(is_published=True)
        page = self.client.get(reverse('spetskurs:task_list')).content.decode()
        self.assertIn('1 материал', page)
        self.assertNotIn('разбор готовится', page)

    def test_landing_card_matches_task_list(self):
        page = self.client.get(reverse('spetskurs:landing')).content.decode()

        self.assertIn('Разбор готовится', page)
        self.assertNotIn(self.draft.title, page)

    def test_draft_opens_for_teacher_only(self):
        """Вычитывают статью на сайте, а не в поле админки, – но только автор."""
        url = self.draft.get_absolute_url()
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_draft_preview_keeps_its_place_in_the_list(self):
        """Соседи считаются той же функцией, что и сама статья.

        Иначе сайдбар открытого черновика не содержит открытой статьи,
        `current_index` падает в 0, и «дальше» ведёт к соседу чужой статьи.
        """
        second = Article.objects.create(
            slug='pendulum-scheme', title='Численный метод',
            track='spetskurs', course_task=self.task, order=2, is_published=False,
        )
        self.client.force_login(self.teacher)
        response = self.client.get(self.draft.get_absolute_url())

        siblings = response.context['sidebar_items']
        self.assertEqual([i['article'].pk for i in siblings], [self.draft.pk, second.pk])
        self.assertEqual(response.context['next_article'], second)

        # Ученику список по-прежнему собирается только из опубликованного.
        Article.objects.filter(pk=second.pk).update(is_published=True)
        self.client.force_login(self.student)
        siblings = self.client.get(second.get_absolute_url()).context['sidebar_items']
        self.assertEqual([i['article'].pk for i in siblings], [second.pk])


class SimulationWheelTest(SimpleTestCase):
    """Колесо над кадром масштабирует график, а страница стоит.

    Библиотека курса уже возвращает EM_TRUE («не выполнять действие по
    умолчанию»), но вешает обработчик колеса на window внутри iframe, а Chrome
    делает такие слушатели пассивными – и preventDefault() там молча
    игнорируется. Наш слушатель отличается от него ровно `{passive: false}`,
    поэтому выглядит дублирующим и первым просится под нож – а без него график
    масштабируется и страница уезжает одновременно.
    """

    def test_wheel_listener_is_not_passive(self):
        frame = Path('templates/spetskurs/_simulation_frame.html').read_text(encoding='utf-8')

        self.assertIn('holdWheel()', frame, 'слушатель колеса не ставится')
        self.assertIn("addEventListener('load', () => this.holdWheel())", frame,
                      'слушатель не переставляется после reload(): src меняется, документ новый')
        self.assertIn('{ passive: false }', frame,
                      'без явного passive: false Chrome игнорирует preventDefault')


class PublishSpetskursCommandTests(TestCase):
    """`publish_spetskurs` – единственный способ выпустить разбор мимо админки.

    seed-команда всегда создаёт черновик, поэтому без выпуска задача навсегда
    остаётся с «разбор готовится». Сторожим две вещи: выпуск доходит до базы, а
    опечатка в слаге падает, а не отчитывается «готово» с нулём обновлённых
    строк.
    """

    @classmethod
    def setUpTestData(cls):
        cls.task = CourseTask.objects.create(
            slug='ballistics', title='Движение под углом к горизонту', number=1,
        )
        cls.first, cls.second = (Article.objects.create(
            slug=slug, title=title, track='spetskurs',
            course_task=cls.task, order=order, is_published=False,
        ) for order, (slug, title) in enumerate(
            [('ballistics-1', 'Физика'), ('ballistics-2', 'Шаг по времени')], start=1
        ))

    def test_named_article_published_alone(self):
        call_command('publish_spetskurs', 'ballistics', 'ballistics-1', stdout=StringIO())

        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertTrue(self.first.is_published)
        self.assertFalse(self.second.is_published, 'выпущено больше, чем названо')

    def test_whole_task_published_without_slugs(self):
        call_command('publish_spetskurs', 'ballistics', stdout=StringIO())

        self.assertEqual(Article.objects.filter(is_published=True).count(), 2)

    def test_typo_raises(self):
        for args in (('ballistics', 'ballistics-9'), ('ballistiks',)):
            with self.assertRaises(CommandError):
                call_command('publish_spetskurs', *args, stdout=StringIO())

        self.assertFalse(Article.objects.filter(is_published=True).exists())
