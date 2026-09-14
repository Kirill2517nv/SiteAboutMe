"""Тесты учебника. Запуск: python manage.py test textbook"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from quizzes.models import Question, Quiz
from textbook.models import Section
from textbook.services import (
    course_map,
    frontier_positions,
    quiz_is_locked,
    shuffle_choices,
    sync_question_texts,
)
from textbook.templatetags.textbook_tags import markdownify


class UngluedListsTest(SimpleTestCase):
    """Список, приклеенный к абзацу без пустой строки, всё равно должен стать <ul>.

    Контент учебника написан именно так, а чистый Markdown в этом случае видит
    продолжение абзаца — с nl2br дефисы выводились как текст.
    """

    def test_list_glued_to_paragraph_becomes_list(self):
        html = markdownify('Встречается на каждом шагу:\n'
                           '- азбука Морзе;\n'
                           '- картотека в библиотеке.')
        self.assertIn('<ul>', html)
        self.assertEqual(html.count('<li>'), 2)

    def test_numbered_list_too(self):
        html = markdownify('Порядок такой:\n1. выборка;\n2. декодирование.')
        self.assertIn('<ol>', html)
        self.assertEqual(html.count('<li>'), 2)

    def test_normal_markdown_still_works(self):
        html = markdownify('Абзац.\n\n- пункт;\n- пункт.')
        self.assertEqual(html.count('<li>'), 2)

    def test_dashes_inside_fenced_code_are_not_touched(self):
        """В блоках кода дефис начинает строку столбика вычитания, не список."""
        html = markdownify('Вычитание единицы:\n\n```\n  00001100   (12)\n'
                           '- 00000001   (1)\n= 00001011   (11)\n```')
        self.assertNotIn('<li>', html)
        self.assertIn('<code>', html)


class SyncQuestionTextsTest(TestCase):
    """Условия задач должны обновляться и там, где ответы учеников уже есть."""

    def setUp(self):
        self.quiz = Quiz.objects.create(title='Практикум', slug='p-test')
        for i in (1, 2):
            Question.objects.create(quiz=self.quiz, question_type='text',
                                    title=f'Задача {i}', text=f'Старое условие {i}')

    def test_texts_updated_in_place(self):
        specs = [dict(title='Задача 1', text='Новое **условие** 1'),
                 dict(title='Задача 2', text='Новое **условие** 2')]
        self.assertEqual(sync_question_texts(self.quiz, specs), 2)
        self.assertEqual(
            [q.text for q in self.quiz.questions.order_by('id')],
            ['Новое **условие** 1', 'Новое **условие** 2'],
        )

    def test_nothing_touched_when_count_differs(self):
        """Набор задач правили руками — сопоставлять по порядку уже нельзя."""
        self.assertEqual(sync_question_texts(self.quiz, [dict(title='Задача 1', text='X')]), 0)
        self.assertEqual(self.quiz.questions.order_by('id').first().text, 'Старое условие 1')


class GradeScaleTest(SimpleTestCase):
    """Шкала «сколько задач на какую оценку» — то, что видит ученик в блоке."""

    section = Section(grade_5_from=12, grade_4_from=9, grade_3_from=6)

    def test_shows_all_thresholds_with_reached_marked(self):
        scale = self.section.grade_scale(7)
        self.assertEqual([(s['grade'], s['need'], s['reached']) for s in scale],
                         [(5, 12, False), (4, 9, False), (3, 6, True)])

    def test_no_scale_without_thresholds(self):
        self.assertEqual(Section().grade_scale(5), [])


class FrontierPositionsTest(TestCase):
    """Аватарка едет только по непрерывному маршруту от начала учебника."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        from accounts.models import Profile, StudentGroup
        from textbook.models import Article, ArticleProgress, ArticleQuiz

        cls.group = StudentGroup.objects.create(name='11А')
        cls.student = User.objects.create_user('vasya')
        Profile.objects.update_or_create(user=cls.student, defaults={'group': cls.group})

        section = Section.objects.create(title='Блок 1', slug='b1', order=1, is_published=True)
        cls.articles = [
            Article.objects.create(section=section, slug=f'a{i}', title=f'Урок {i}',
                                   order=i, is_published=True)
            for i in (1, 2, 3)
        ]
        # У первых двух статей есть самопроверка на 2 вопроса, у третьей теста нет.
        cls.quizzes = []
        for article in cls.articles[:2]:
            quiz = Quiz.objects.create(title=f'СП {article.slug}', is_self_check=True)
            for n in (1, 2):
                Question.objects.create(quiz=quiz, text=f'Вопрос {n}', correct_text_answer='1')
            ArticleQuiz.objects.create(article=article, quiz=quiz)
            cls.quizzes.append(quiz)
        cls.progress_model = ArticleProgress

    def solve(self, quiz, correct_count):
        from quizzes.models import UserAnswer, UserResult

        result = UserResult.objects.create(user=self.student, quiz=quiz, score=correct_count)
        for i, question in enumerate(quiz.questions.order_by('id')):
            UserAnswer.objects.create(user_result=result, question=question,
                                      text_answer='1', is_correct=i < correct_count)

    def position(self):
        positions = frontier_positions([self.group.id])
        return next((aid for aid, users in positions.items() if self.student in users), None)

    def test_starts_at_first_article(self):
        self.assertEqual(self.position(), self.articles[0].id)

    def test_half_correct_is_enough_to_move_on(self):
        """Жёлтый уровень (1 из 2) уже засчитывается — это и есть порог «более 50%»."""
        self.solve(self.quizzes[0], 1)
        self.assertEqual(self.position(), self.articles[1].id)

    def test_below_half_does_not_move(self):
        self.solve(self.quizzes[0], 0)
        self.assertEqual(self.position(), self.articles[0].id)

    def test_jump_ahead_does_not_move_the_pin(self):
        """Ученик перепрыгнул на второй урок — фишка осталась на первом."""
        self.solve(self.quizzes[1], 2)
        self.assertEqual(self.position(), self.articles[0].id)

    def test_article_without_self_check_falls_back_to_read(self):
        self.solve(self.quizzes[0], 2)
        self.solve(self.quizzes[1], 2)
        self.assertEqual(self.position(), self.articles[2].id)
        self.progress_model.objects.create(user=self.student, article=self.articles[2],
                                           status='read')
        self.assertIsNone(self.position(), 'маршрут пройден целиком — фишки быть не должно')

    def test_other_groups_are_invisible(self):
        self.assertEqual(frontier_positions([self.group.id + 99]), {})
        self.assertEqual(frontier_positions([]), {})


class OpenSectionTest(TestCase):
    """Главная учебника раскрывает блок, где стоит фишка ученика."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        from accounts.models import Profile, StudentGroup
        from textbook.models import Article, ArticleProgress

        cls.group = StudentGroup.objects.create(name='11Б')
        cls.student = User.objects.create_user('petya', password='pw')
        Profile.objects.update_or_create(user=cls.student, defaults={'group': cls.group})

        cls.sections = [
            Section.objects.create(title=f'Блок {i}', slug=f'ob{i}', order=i, is_published=True)
            for i in (1, 2)
        ]
        cls.articles = [
            Article.objects.create(section=section, slug=f'oa{i}', title=f'Урок {i}',
                                   order=1, is_published=True)
            for i, section in enumerate(cls.sections, start=1)
        ]
        cls.progress_model = ArticleProgress

    def open_orders(self, login=True):
        if login:
            self.client.force_login(self.student)
        rows = self.client.get('/textbook/').context['material_sections']
        return [row['section'].order for row in rows if row['is_open']]

    def test_first_block_is_open_at_the_start(self):
        self.assertEqual(self.open_orders(), [1])

    def test_open_block_follows_the_pin(self):
        self.progress_model.objects.create(user=self.student, article=self.articles[0],
                                           status='read')
        self.assertEqual(self.open_orders(), [2],
                         'первый блок пройден – раскрыт второй, как и едет аватарка')

    def test_deadline_does_not_move_the_open_block(self):
        """Дедлайн фишку не двигает: непрочитанный блок остаётся раскрытым и после него.

        Отличие от метки «вы здесь» на главной (`course_map`), которая по
        прошедшему дедлайну уезжает вперёд, – здесь ученика возвращают туда,
        где он реально встал.
        """
        self.sections[0].deadline = timezone.now() - timedelta(days=1)
        self.sections[0].save(update_fields=['deadline'])
        self.assertEqual(self.open_orders(), [1])

    def test_finished_course_falls_back_to_the_first_block(self):
        for article in self.articles:
            self.progress_model.objects.create(user=self.student, article=article, status='read')
        self.assertEqual(self.open_orders(), [1], 'фишки нет – раскрыт ровно один блок')

    def test_guest_gets_the_first_block(self):
        self.assertEqual(self.open_orders(login=False), [1])


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class SectionExtensionTest(TestCase):
    """Личное продление дедлайна блока: болевший досдаёт, остальной класс закрыт."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        from textbook.models import Article, ArticleQuiz

        cls.ill = User.objects.create_user('ill', password='pw')
        cls.other = User.objects.create_user('other', password='pw')

        cls.past = timezone.now() - timedelta(days=3)
        cls.section = Section.objects.create(
            title='Блок с дедлайном', slug='se1', order=1, is_published=True,
            deadline=cls.past,
        )
        cls.practicum = Quiz.objects.create(title='Практикум', is_public=True)
        Question.objects.create(quiz=cls.practicum, text='2+2', correct_text_answer='4')
        cls.section.practicum_quiz = cls.practicum
        cls.section.save(update_fields=['practicum_quiz'])

        cls.next_section = Section.objects.create(
            title='Следующий блок', slug='se2', order=2, is_published=True,
        )
        Article.objects.create(section=cls.next_section, slug='sa2', title='Урок 2',
                               order=1, is_published=True)

        cls.article = Article.objects.create(section=cls.section, slug='sa1', title='Урок',
                                             order=1, is_published=True)
        cls.self_check = Quiz.objects.create(title='Самопроверка', is_self_check=True)
        Question.objects.create(quiz=cls.self_check, text='3+3', correct_text_answer='6')
        ArticleQuiz.objects.create(article=cls.article, quiz=cls.self_check)

    def extend(self, days=7, user=None):
        from textbook.models import SectionExtension

        return SectionExtension.objects.create(
            user=user or self.ill, section=self.section,
            deadline=timezone.now() + timedelta(days=days), reason='болел',
        )

    def test_common_deadline_locks_everyone(self):
        self.assertTrue(quiz_is_locked(self.practicum, self.ill))
        self.assertTrue(quiz_is_locked(self.self_check, self.ill))

    def test_extension_opens_practicum_and_self_check(self):
        self.extend()
        self.assertFalse(quiz_is_locked(self.practicum, self.ill))
        self.assertFalse(quiz_is_locked(self.self_check, self.ill),
                         'самопроверки урока закрываются тем же дедлайном')
        self.assertTrue(quiz_is_locked(self.practicum, self.other),
                        'продление одному не открывает блок всему классу')

    def test_extension_only_extends(self):
        """Личная дата раньше общей ничего не закрывает и не открывает."""
        from textbook.models import SectionExtension

        SectionExtension.objects.create(user=self.ill, section=self.section,
                                        deadline=self.past - timedelta(days=5))
        self.assertTrue(quiz_is_locked(self.practicum, self.ill))

        self.section.deadline = timezone.now() + timedelta(days=1)
        self.section.save(update_fields=['deadline'])
        self.assertFalse(quiz_is_locked(self.practicum, self.ill),
                         'общий дедлайн ещё не прошёл – продление не может закрыть блок')

    def test_extension_without_common_deadline_changes_nothing(self):
        self.section.deadline = None
        self.section.save(update_fields=['deadline'])
        self.extend(days=-5)
        self.assertFalse(quiz_is_locked(self.practicum, self.ill),
                         'у блока без дедлайна закрывать нечего')

    def test_page_is_read_only_after_deadline_and_editable_after_extension(self):
        url = f'/quizzes/{self.self_check.id}/'
        self.client.force_login(self.ill)
        self.assertTrue(self.client.get(url).context['read_only'])
        self.extend()
        self.assertFalse(self.client.get(url).context.get('read_only'))

    def test_student_sees_his_own_date(self):
        from textbook.services import profile_textbook_stats

        self.extend()
        row = next(s for s in profile_textbook_stats(self.ill)['sections']
                   if s['section'].id == self.section.id)
        self.assertFalse(row['is_closed'])
        self.assertGreater(row['deadline'], self.past)

        other = next(s for s in profile_textbook_stats(self.other)['sections']
                     if s['section'].id == self.section.id)
        self.assertTrue(other['is_closed'])
        self.assertEqual(other['deadline'], self.past)

    def test_pin_stays_on_an_extended_block(self):
        """Метка «вы здесь» уезжает по дедлайну – но не у того, кому продлили."""
        self.assertFalse(any(r['is_current'] and r['section'].id == self.section.id
                             for r in course_map(self.other)))
        self.extend()
        self.assertTrue(any(r['is_current'] and r['section'].id == self.section.id
                            for r in course_map(self.ill)))


class ShuffleChoicesTest(SimpleTestCase):
    """Варианты ответа перемешиваются: в сидах правильный всегда написан первым.

    Порядок обязан быть детерминированным — иначе каждый прогон
    seed_textbook_blockN переставлял бы ученику варианты заново.
    """

    CHOICES = [('верно', True), ('неверно', False), ('тоже нет', False), ('и нет', False)]

    def test_order_is_stable_for_same_question(self):
        first = shuffle_choices('Сколько будет 2 + 2?', self.CHOICES)
        second = shuffle_choices('Сколько будет 2 + 2?', self.CHOICES)
        self.assertEqual(first, second)

    def test_nothing_is_lost_or_duplicated(self):
        self.assertEqual(sorted(shuffle_choices('вопрос', self.CHOICES)), sorted(self.CHOICES))

    def test_correct_answer_is_not_always_first(self):
        positions = set()
        for i in range(30):
            mixed = shuffle_choices('Вопрос номер %d' % i, self.CHOICES)
            positions.add(next(n for n, c in enumerate(mixed) if c[1]))
        self.assertEqual(positions, {0, 1, 2, 3})

    def test_input_list_is_not_mutated(self):
        original = list(self.CHOICES)
        shuffle_choices('вопрос', self.CHOICES)
        self.assertEqual(self.CHOICES, original)


class HintStateTest(TestCase):
    """Подсказка не существует для ученика, пока он не упрётся в задачу сам."""

    def setUp(self):
        from django.contrib.auth.models import User

        self.user = User.objects.create_user('vasya', password='x')
        self.quiz = Quiz.objects.create(title='Практикум', is_self_check=True)
        self.section = Section.objects.create(
            title='Блок', slug='blok-test', practicum_quiz=self.quiz, is_published=True
        )
        self.question = Question.objects.create(
            quiz=self.quiz, question_type='code', title='Задача 1',
            text='Условие', hint='Разложите число на цифры.',
        )

    def _fail(self, times):
        from quizzes.models import CodeSubmission

        for _ in range(times):
            CodeSubmission.objects.create(
                user=self.user, question=self.question, quiz=self.quiz,
                code='print()', status='failed',
            )

    def test_closed_until_three_failures(self):
        from textbook.services import hint_state

        self.assertIsNone(hint_state(self.user, self.question))
        self._fail(2)
        self.assertIsNone(hint_state(self.user, self.question))
        self._fail(1)
        self.assertEqual(hint_state(self.user, self.question), 'offer')

    def test_choice_is_remembered(self):
        from quizzes.models import HintChoice
        from textbook.services import hint_state

        self._fail(3)
        HintChoice.objects.create(user=self.user, question=self.question, accepted=False)
        self.assertEqual(hint_state(self.user, self.question), 'declined')
        HintChoice.objects.update(accepted=True)
        self.assertEqual(hint_state(self.user, self.question), 'taken')

    def test_deadline_and_switch_open_without_failures(self):
        from datetime import timedelta

        from django.utils import timezone

        from textbook.services import hint_state

        self.section.deadline = timezone.now() + timedelta(days=4)
        self.section.save(update_fields=['deadline'])
        self.assertIsNone(hint_state(self.user, self.question))

        self.section.deadline = timezone.now() + timedelta(days=2)
        self.section.save(update_fields=['deadline'])
        self.assertEqual(hint_state(self.user, self.question), 'offer')

        self.section.deadline = None
        self.section.hints_open = True
        self.section.save(update_fields=['deadline', 'hints_open'])
        self.assertEqual(hint_state(self.user, self.question), 'offer')

    def test_view_does_not_leak_text_before_choice(self):
        self.client.force_login(self.user)
        url = f'/quizzes/question/{self.question.id}/hint/'

        # Закрыта: ни состояния, ни текста.
        data = self.client.get(url).json()
        self.assertIsNone(data['state'])
        self.assertNotIn('hint', data)

        # Открыта, но выбор не сделан — текста всё ещё нет.
        self._fail(3)
        data = self.client.get(url).json()
        self.assertEqual(data['state'], 'offer')
        self.assertNotIn('hint', data)

        # Отказ фиксируется, текст не отдаётся.
        data = self.client.post(url, '{"action": "decline"}',
                                content_type='application/json').json()
        self.assertEqual(data['state'], 'declined')
        self.assertNotIn('hint', data)

        # Согласие — текст приходит.
        data = self.client.post(url, '{"action": "take"}',
                                content_type='application/json').json()
        self.assertEqual(data['state'], 'taken')
        self.assertIn('цифры', data['hint'])

    def test_hidden_section_hides_hint_even_when_block_is_open(self):
        """Рубильник «подсказки блока» открыт, но сам блок ещё не показан ученикам.

        Условия открытия подсказки блочные и не зависят от попыток ученика,
        поэтому без проверки публикации перебор question_id вытаскивал бы
        подсказки к задачам ненапечатанных блоков.
        """
        self.section.hints_open = True
        self.section.is_published = False
        self.section.save(update_fields=['hints_open', 'is_published'])

        self.client.force_login(self.user)
        url = f'/quizzes/question/{self.question.id}/hint/'
        data = self.client.post(url, '{"action": "take"}',
                                content_type='application/json').json()
        self.assertIsNone(data['state'])
        self.assertNotIn('hint', data)


# Манифест whitenoise существует только после collectstatic — тестам, которые
# дорисовывают страницу до конца, хватит обычной раздачи статики.
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class HiddenSectionAccessTest(TestCase):
    """Спрятанный блок не отдаёт содержимое по прямым ссылкам.

    На главной его нет, но URL статьи и id теста предсказуемы — гейт должен
    стоять во вьюхах, а не только в списке.
    """

    def setUp(self):
        from django.contrib.auth.models import User

        from textbook.models import Article

        self.user = User.objects.create_user('petya', password='x')
        self.quiz = Quiz.objects.create(title='Практикум 13', is_self_check=True)
        self.hidden = Section.objects.create(
            title='Блок 13', slug='blok-13', order=13,
            practicum_quiz=self.quiz, is_published=False,
        )
        self.article = Article.objects.create(
            track='material', section=self.hidden, slug='13-1-grafy',
            title='Что такое граф?', order=1, is_published=True,
        )

    def test_article_of_hidden_section_is_404(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/textbook/article/13-1-grafy/').status_code, 404)

    def test_progress_endpoints_reject_hidden_article(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post('/textbook/article/13-1-grafy/read/').status_code, 404)
        self.assertEqual(
            self.client.post('/textbook/article/13-1-grafy/time/', {'seconds': 60}).status_code,
            404)

    def test_practicum_of_hidden_section_is_not_accessible(self):
        from textbook.services import quiz_is_hidden

        self.assertTrue(quiz_is_hidden(self.quiz))
        self.client.force_login(self.user)
        response = self.client.get(f'/quizzes/{self.quiz.id}/')
        self.assertEqual(response.status_code, 302)

    def test_teacher_can_proofread_hidden_block(self):
        """Учитель вычитывает неопубликованный блок на самом сайте, а не в админке."""
        from django.contrib.auth.models import User

        teacher = User.objects.create_superuser('teacher', 'a@b.c', 'x')
        self.client.force_login(teacher)
        self.assertEqual(self.client.get('/textbook/article/13-1-grafy/').status_code, 200)
        self.assertEqual(self.client.get(f'/quizzes/{self.quiz.id}/').status_code, 200)

    def test_publishing_the_section_opens_everything(self):
        self.hidden.is_published = True
        self.hidden.save(update_fields=['is_published'])

        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/textbook/article/13-1-grafy/').status_code, 200)
        self.assertEqual(self.client.get(f'/quizzes/{self.quiz.id}/').status_code, 200)


class ReadingTimeTest(TestCase):
    """Время чтения ограничено серверными часами, а не только размером порции."""

    def setUp(self):
        from django.contrib.auth.models import User

        from textbook.models import Article

        self.user = User.objects.create_user('masha', password='x')
        self.section = Section.objects.create(
            title='Блок 1', slug='blok-1', order=1, is_published=True)
        self.article = Article.objects.create(
            track='material', section=self.section, slug='1-1-vvedenie',
            title='Введение', order=1, is_published=True,
        )
        self.client.force_login(self.user)

    def _post(self, seconds):
        return self.client.post('/textbook/article/1-1-vvedenie/time/', {'seconds': seconds})

    def test_repeated_posts_cannot_inflate_time(self):
        from textbook.models import ArticleProgress

        for _ in range(10):
            self._post(300)

        total = ArticleProgress.objects.get(user=self.user, article=self.article).time_spent_seconds
        # Первая порция идёт целиком (прогресса ещё не было), дальше бюджет
        # упирается в реально прошедшее время — то есть почти в ноль.
        self.assertLess(total, 400)


class CourseMapPinTest(TestCase):
    """Метка «вы здесь» на главной: когда блок её отпускает.

    Правило двойное: либо практикум сдан минимум на тройку И в следующем блоке
    открыта хотя бы одна статья, либо у блока прошёл дедлайн – тогда двигаем
    принудительно, задачи всё равно больше не принимаются.
    """

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        from textbook.models import Article

        cls.student = User.objects.create_user('petya')

        # Пороги как у боевого блока 1: 5 – от 18, 4 – от 17, 3 – от 16.
        cls.practicum = Quiz.objects.create(title='Практикум блока 1')
        for n in range(18):
            Question.objects.create(quiz=cls.practicum, text=f'Задача {n}',
                                    correct_text_answer='1')
        cls.s1 = Section.objects.create(
            title='Блок 1', slug='cm1', order=1, is_published=True,
            practicum_quiz=cls.practicum,
            grade_5_from=18, grade_4_from=17, grade_3_from=16,
        )
        cls.s2 = Section.objects.create(title='Блок 2', slug='cm2', order=2,
                                        is_published=True)
        for section, prefix in ((cls.s1, 'cm1'), (cls.s2, 'cm2')):
            for i in (1, 2):
                Article.objects.create(section=section, slug=f'{prefix}-a{i}',
                                       title=f'Урок {i}', order=i, is_published=True)

    def solve(self, count):
        """Засчитать ученику `count` задач практикума."""
        from quizzes.models import UserAnswer, UserResult

        UserResult.objects.filter(user=self.student, quiz=self.practicum).delete()
        result = UserResult.objects.create(user=self.student, quiz=self.practicum, score=count)
        for question in self.practicum.questions.all()[:count]:
            UserAnswer.objects.create(user_result=result, question=question,
                                      text_answer='1', is_correct=True)

    def start_second_block(self):
        from textbook.models import ArticleProgress

        ArticleProgress.objects.create(
            user=self.student, article=self.s2.articles.first(), status='reading')

    def pin(self):
        rows = course_map(self.student)
        current = next((r for r in rows if r['is_current']), None)
        return current['section'].order if current else None

    def test_pin_stays_while_grade_below_three(self):
        self.solve(15)
        self.start_second_block()
        self.assertEqual(self.pin(), 1)

    def test_pin_stays_until_next_block_is_opened(self):
        """Тройка есть, но следующий блок не открывали – метка не убегает вперёд."""
        self.solve(16)
        self.assertEqual(self.pin(), 1)

    def test_pin_moves_on_grade_three_and_started_next(self):
        self.solve(16)
        self.start_second_block()
        self.assertEqual(self.pin(), 2)

    def test_deadline_moves_pin_regardless_of_progress(self):
        """После дедлайна метка уходит, даже если задачи не решены совсем."""
        from datetime import timedelta

        from django.utils import timezone

        Section.objects.filter(pk=self.s1.pk).update(
            deadline=timezone.now() - timedelta(days=1))
        self.assertEqual(self.pin(), 2)

    def test_pin_stays_on_last_block_even_after_deadline(self):
        """Переезжать некуда: следующего опубликованного блока нет."""
        from datetime import timedelta

        from django.utils import timezone

        Section.objects.filter(pk=self.s2.pk).update(is_published=False)
        Section.objects.filter(pk=self.s1.pk).update(
            deadline=timezone.now() - timedelta(days=1))
        self.assertEqual(self.pin(), 1)

    def test_guest_has_no_pin(self):
        """У гостя прогресса нет – метку ставить не на что."""
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(any(row['is_current'] for row in course_map(AnonymousUser())))


# Тот же обход манифеста, что и выше: страница подключает статику.
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ArticlePresentModeTests(TestCase):
    """Режим проектора на странице урока.

    Слайд – это блок статьи, отдельного хранилища у презентации нет. Тест
    сторожит именно связь: если разметку блоков поправят и data-slide отвалится,
    страница на проекторе перестанет листаться молча – в браузере это видно
    только у доски.
    """

    @classmethod
    def setUpTestData(cls):
        from textbook.models import Article, ArticleBlock

        section = Section.objects.create(title='Блок 1', slug='pm1', order=1,
                                         is_published=True)
        cls.article = Article.objects.create(
            section=section, slug='pm-a1', title='Урок 1', order=1, is_published=True)
        for i, title in enumerate(['С чего всё пошло', '', 'Итоги']):
            ArticleBlock.objects.create(article=cls.article, block_type='text',
                                        title=title, content='Текст.', order=i)

    def setUp(self):
        self.html = self.client.get(self.article.get_absolute_url()).content.decode()

    def test_page_hosts_present_component(self):
        self.assertIn('present-root', self.html)
        self.assertIn('articlePresent()', self.html)
        self.assertIn('js/present-mode.js', self.html)
        self.assertIn('js/article-present.js', self.html)

    def test_every_block_is_a_slide(self):
        self.assertEqual(self.html.count('<article data-slide'), self.article.blocks.count())

    def test_service_chrome_is_hidden_on_the_projector(self):
        """Сайдбар и хвост страницы помечены present-hide."""
        self.assertIn('article-sidebar-col hidden md:block present-hide', self.html)
        self.assertGreaterEqual(self.html.count('present-hide'), 5)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class SolutionBlockTests(TestCase):
    """Разбор задания в статье: закрыт до занятия, открывает его учитель.

    Три роли и три разных ответа, поэтому и тестов столько: гостю блока нет
    вовсе, ученик видит заглушку без решения, учитель – решение и рубильник.
    Главное, что здесь сторожится: текст разбора не должен доехать до чужого
    браузера даже в исходнике страницы – спрятать его стилями значит отдать.
    """

    SOLUTION = 'Ответ: 35.8 градуса'

    @classmethod
    def setUpTestData(cls):
        from textbook.models import Article, ArticleBlock

        section = Section.objects.create(title='Блок 1', slug='sol1', order=1,
                                         is_published=True)
        cls.article = Article.objects.create(
            section=section, slug='sol-a1', title='Задания', order=1, is_published=True)
        ArticleBlock.objects.create(article=cls.article, block_type='text',
                                    title='1. Задание', content='Условие.', order=1)
        cls.solution = ArticleBlock.objects.create(
            article=cls.article, block_type='text', title='Разбор задания 1',
            content=cls.SOLUTION, order=2, visibility='teacher')
        cls.student = User.objects.create_user('pupil', password='pw')
        cls.teacher = User.objects.create_superuser('teacher', password='pw')

    def _html(self, user=None):
        if user:
            self.client.force_login(user)
        else:
            self.client.logout()
        return self.client.get(self.article.get_absolute_url()).content.decode()

    def _toggle_url(self):
        return reverse('textbook:block_visibility_toggle', args=[self.solution.pk])

    def test_guest_gets_no_block_at_all(self):
        html = self._html()
        self.assertNotIn(self.SOLUTION, html)
        self.assertNotIn('article-solution', html)

    def test_student_sees_placeholder_without_the_answer(self):
        html = self._html(self.student)
        self.assertIn('article-solution', html)
        self.assertIn('Разбор откроем на занятии', html)
        self.assertNotIn(self.SOLUTION, html)

    def test_panel_folds_away(self):
        """Разбор занимает экран, поэтому панель сворачивается – нативным
        <details>, чтобы работало и без JS, и на проекторе."""
        html = self._html(self.teacher)
        self.assertIn('<details class="article-solution', html)
        self.assertIn('<summary class="article-solution__head"', html)
        # Свёрнута при открытии страницы: разбор не должен попадаться на глаза
        # раньше, чем задание решено, – ни ученику, ни учителю у доски.
        self.assertNotIn('article-solution" open', html)

    def test_teacher_sees_the_answer_and_the_switch(self):
        html = self._html(self.teacher)
        self.assertIn(self.SOLUTION, html)
        self.assertIn(self._toggle_url(), html)
        self.assertIn('видно только вам', html)

    def test_only_teacher_may_open_it(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(self._toggle_url()).status_code, 403)
        self.solution.refresh_from_db()
        self.assertEqual(self.solution.visibility, 'teacher')

    def test_opened_reaches_students_but_never_guests(self):
        self.client.force_login(self.teacher)
        self.client.post(self._toggle_url())
        self.solution.refresh_from_db()
        self.assertEqual(self.solution.visibility, 'students')

        self.assertIn(self.SOLUTION, self._html(self.student))
        self.assertNotIn(self.SOLUTION, self._html(), 'решение утекло гостю')

    def test_switch_closes_it_back(self):
        self.client.force_login(self.teacher)
        self.client.post(self._toggle_url())
        self.client.post(self._toggle_url())
        self.solution.refresh_from_db()
        self.assertEqual(self.solution.visibility, 'teacher')

    def test_ordinary_block_has_nothing_to_open(self):
        """У блока «всем» нет закрытого состояния – рубильник не должен его выдумывать."""
        plain = self.article.blocks.get(order=1)
        self.client.force_login(self.teacher)
        url = reverse('textbook:block_visibility_toggle', args=[plain.pk])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_reseeding_the_text_keeps_it_open(self):
        """Сид правит формулировки; открытый разбор он закрывать не должен.

        replace_blocks сносит блоки и создаёт заново – без переноса видимости
        очередная правка опечатки тихо забрала бы у класса разобранный ответ.
        """
        from textbook.services import replace_blocks

        self.solution.visibility = 'students'
        self.solution.save(update_fields=['visibility'])

        replace_blocks(self.article, [
            dict(block_type='text', title='1. Задание', content='Условие.', order=1),
            dict(block_type='text', title='Разбор задания 1', order=2,
                 content=self.SOLUTION + ' (поправили опечатку)', visibility='teacher'),
        ])
        self.assertEqual(self.article.blocks.get(order=2).visibility, 'students')


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ArticleLeadTests(TestCase):
    """Первый текстовый блок рисуется вводкой – кроме статьи-списка заданий.

    Синяя карточка вводки означает «это предисловие ко всему, что ниже».
    В статье с заданиями предисловия нет, она открывается сразу пунктом «1. …»,
    и первый пункт в этой карточке читался бы как введение к остальным семи.
    Правило держится на заголовке блока, поэтому и сторожим его заголовком:
    условие в шаблоне легко «упростить» обратно, а увидеть это можно только
    открыв статью заданий глазами.
    """

    @classmethod
    def setUpTestData(cls):
        from textbook.models import Article, ArticleBlock

        section = Section.objects.create(title='Блок 1', slug='lead1', order=1,
                                         is_published=True)
        cls.lesson = Article.objects.create(
            section=section, slug='lead-a1', title='Урок', order=1, is_published=True)
        ArticleBlock.objects.create(article=cls.lesson, block_type='text',
                                    title='С чего всё пошло', content='Текст.', order=1)

        cls.tasks = Article.objects.create(
            section=section, slug='lead-a2', title='Задания', order=2, is_published=True)
        for i, title in enumerate(['1. Попасть в мишень', '2. Максимум дальности'], start=1):
            ArticleBlock.objects.create(article=cls.tasks, block_type='text',
                                        title=title, content='Текст.', order=i)

    def _html(self, article):
        return self.client.get(article.get_absolute_url()).content.decode()

    def test_ordinary_article_keeps_the_lead(self):
        html = self._html(self.lesson)
        self.assertIn('article-lead', html)
        self.assertIn('С чего всё пошло', html)

    def test_task_list_opens_without_the_lead(self):
        html = self._html(self.tasks)
        self.assertNotIn('article-lead', html)

    def test_task_list_keeps_its_heading(self):
        """Без карточки заголовок обязан вернуться в обычный h2 – иначе
        первый пункт остался бы вовсе без названия."""
        self.assertIn('<h2 class="article-block-title">1. Попасть в мишень</h2>',
                      self._html(self.tasks))


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ArticleBlockTitleTests(TestCase):
    """Бэктики в заголовке блока – это код, а не бэктики.

    Уроки про методы и операторы состоят из кода прямо в заголовке
    («`find()` и `rfind()`: где именно стоит кусок»), и выводились они сырым
    текстом вместе с бэктиками – в блоках 6, 8 и 13 сразу. Полный markdown
    тут не подходит и первым просится вместо узкого фильтра: заголовок
    «1. Попасть в мишень» он превращает в нумерованный список внутри h2.
    """

    @classmethod
    def setUpTestData(cls):
        from textbook.models import Article, ArticleBlock

        section = Section.objects.create(title='Блок', slug='ttl', order=1,
                                         is_published=True)
        cls.article = Article.objects.create(
            section=section, slug='ttl-a1', title='Урок', order=1, is_published=True)
        ArticleBlock.objects.create(article=cls.article, block_type='text',
                                    title='Вводка', content='Текст.', order=1)
        for order, title in enumerate(
            ['`find()` и `rfind()`: где именно', 'Побитовое И (`&`)', '2. Без кода'],
            start=2,
        ):
            ArticleBlock.objects.create(article=cls.article, block_type='text',
                                        title=title, content='Текст.', order=order)

    def _html(self):
        return self.client.get(self.article.get_absolute_url()).content.decode()

    def test_backticks_become_code(self):
        html = self._html()
        self.assertIn('<code>find()</code> и <code>rfind()</code>: где именно', html)
        self.assertNotIn('`find()`', html)

    def test_special_characters_stay_escaped(self):
        """Заголовок `&` – это амперсанд, а не начало HTML-мнемоники."""
        self.assertIn('Побитовое И (<code>&amp;</code>)', self._html())

    def test_numbered_title_is_not_turned_into_a_list(self):
        self.assertIn('<h2 class="article-block-title">2. Без кода</h2>', self._html())


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class WidgetScriptLoadingTests(TestCase):
    """Реестр виджетов грузится только там, где виджет есть.

    Файл весит 148 КБ gzip, а виджет стоит в четверти статей: на остальных он
    скачивался, не находил ни одного [data-widget] и выходил. Условие в шаблоне
    считается по тому же списку блоков, который шаблон и рисует, – иначе
    появился бы второй способ узнать «есть ли тут виджет», и он бы разошёлся с
    первым. Сторожим обе стороны: где виджета нет – скрипта нет, где есть –
    есть, и вместе с ним наблюдатель MathJax, который живёт ради виджетов.
    """

    SCRIPT = 'js/textbook-widgets.js'

    @classmethod
    def setUpTestData(cls):
        from textbook.models import Article, ArticleBlock

        section = Section.objects.create(title='Блок', slug='wsl', order=1,
                                         is_published=True)
        cls.plain = Article.objects.create(
            section=section, slug='wsl-plain', title='Без виджета', order=1,
            is_published=True)
        ArticleBlock.objects.create(article=cls.plain, block_type='text',
                                    title='Вводка', content='Текст.', order=1)

        cls.rich = Article.objects.create(
            section=section, slug='wsl-rich', title='С виджетом', order=2,
            is_published=True)
        ArticleBlock.objects.create(article=cls.rich, block_type='text',
                                    title='Вводка', content='Текст.', order=1)
        ArticleBlock.objects.create(article=cls.rich, block_type='widget',
                                    widget_key='bits-viewer', order=2)

    def _html(self, article):
        return self.client.get(article.get_absolute_url()).content.decode()

    def test_article_without_widgets_skips_the_script(self):
        html = self._html(self.plain)
        self.assertNotIn(self.SCRIPT, html)
        self.assertNotIn('MathJax.typesetClear', html)

    def test_article_with_widget_loads_the_script(self):
        html = self._html(self.rich)
        self.assertIn(self.SCRIPT, html)
        self.assertIn('data-widget="bits-viewer"', html)
        # Наблюдатель уехал под то же условие – без него формулы внутри
        # виджета остались бы сырым «$...$» после первой же перерисовки.
        self.assertIn('MathJax.typesetClear', html)


class ProjectorFontScaleTest(SimpleTestCase):
    """Шкала кегля статьи должна целиком иметь rem-двойник для проектора.

    Масштаб на проекторе – это корневой font-size, и растёт только то, что
    измерено в rem. Шкала статьи объявлена в px, а её rem-копия живёт в блоке
    .present-root:fullscreen. Добавят седьмую переменную в шкалу и забудут про
    копию – на уроке этот кусок текста останется мелким, и заметит это только
    класс с задней парты.
    """

    def variables(self, selector):
        import re
        from pathlib import Path

        css = Path('static/css/textbook-article.css').read_text(encoding='utf-8')
        # Шкала объявлена одним блоком на селектор; берём последний из них –
        # первое вхождение .article-column задаёт ширину, а не кегль.
        blocks = re.findall(re.escape(selector) + r'\s*\{([^}]*)\}', css)
        return {name for block in blocks for name in re.findall(r'(--fs-[\w-]+)\s*:', block)}

    def test_every_font_variable_has_a_rem_twin(self):
        base = self.variables('.article-column')
        projector = self.variables('.present-root:fullscreen .article-column')
        self.assertTrue(base, 'шкала кегля не найдена – селектор в CSS переименовали?')
        self.assertEqual(base, projector)

    def test_projector_scale_is_in_rem(self):
        import re
        from pathlib import Path

        css = Path('static/css/textbook-article.css').read_text(encoding='utf-8')
        block = re.search(r'\.present-root:fullscreen \.article-column\s*\{([^}]*)\}', css).group(1)
        self.assertNotIn('px', block)
        self.assertEqual(len(re.findall(r'rem', block)), len(re.findall(r'--fs-', block)))


class TemplateCommentsTest(SimpleTestCase):
    """Многострочный {# … #} утекает в отрендеренную страницу.

    Django-тег {# … #} закрывается только в пределах своей строки: всё, что
    ниже первого перевода строки, шаблонизатор считает обычной разметкой и
    отдаёт браузеру. Ошибка тихая – в исходнике текст выглядит комментарием, а
    на странице читается как абзац. Многострочный комментарий пишется
    {% comment %} … {% endcomment %}.
    """

    def test_no_multiline_hash_comments_in_templates(self):
        import re
        from pathlib import Path

        # Открытие, перевод строки и закрытие – без вложенного «#}» между ними.
        pattern = re.compile(r'\{#(?:(?!#\}).)*?\n(?:(?!#\}).)*?#\}', re.S)
        leaks = []
        for path in Path('templates').rglob('*.html'):
            text = path.read_text(encoding='utf-8')
            for match in pattern.finditer(text):
                line = text[:match.start()].count('\n') + 1
                leaks.append(f'{path}:{line}')
        self.assertEqual(leaks, [], 'многострочные {# #} утекут в HTML: ' + ', '.join(leaks))


class FontScaleTest(SimpleTestCase):
    """Кегль в шаблонах – только ступени общей шкалы.

    До неё на страницах жили девять произвольных размеров между 9 и 17px
    (`text-[12.5px]`, `font-size: 13.5px`), и один и тот же подзаголовок был
    12px на одной странице и 18px на соседней. Шкала описана в CLAUDE.md:
    12 / 14 / 16 / 18 / 20 / 24 / 30 / 36 / 48. Тест сторожит её от следующего
    «ну тут на полпикселя мельче» – такие правки не видно в ревью, а вместе
    они и сделали разнобой.
    """

    #: Кегль вне шкалы разрешён там, где буквы работают как графика.
    EXCEPTIONS = {
        # CSS-иллюстрации главной: макет сайта шириной 174px в миниатюре.
        'templates/home.html',
        # Игровое поле «Своей игры» на проекторе – кегль подобран под клетку.
        'templates/games/svoya_igra/play.html',
        # Год выпуска (clamp) и стрелки Swiper – декоративные глифы.
        'templates/accounts/alumni.html',
        'templates/about.html',
    }

    SCALE_PX = {12, 14, 16, 18, 20, 24, 30, 36, 48}

    def files(self):
        from pathlib import Path

        for path in sorted(Path('templates').rglob('*.html')):
            if path.as_posix() in self.EXCEPTIONS:
                continue
            yield path, path.read_text(encoding='utf-8')

    def test_no_arbitrary_tailwind_sizes(self):
        import re

        found = [f'{path}: {m}' for path, text in self.files()
                 for m in re.findall(r'text-\[[^\]]+\]', text)]
        self.assertEqual(found, [], 'произвольный кегль мимо шкалы: ' + ', '.join(found))

    def test_inline_font_size_is_on_the_scale(self):
        import re

        found = []
        for path, text in self.files():
            for value, unit in re.findall(r'font-size:\s*([\d.]+)(px|rem)', text):
                px = float(value) * (16 if unit == 'rem' else 1)
                if px not in self.SCALE_PX:
                    found.append(f'{path}: {value}{unit}')
        self.assertEqual(found, [], 'кегль мимо шкалы: ' + ', '.join(found))


class TruthTableParserTests(SimpleTestCase):
    """Разбор выражения в виджете truth-table – сверка с настоящим Python.

    Виджет умеет строить таблицу по введённому выражению, то есть содержит
    собственный интерпретатор. Он обещает питоновский синтаксис (not/and/or,
    ==, !=, импликация через <=) и питоновский приоритет операций – значит,
    обязан считать ровно то же, что посчитает интерпретатор, иначе учит
    неправде. Поэтому эталоны не выдуманы: выражения ниже прогоняются через
    eval() и передаются проверке как ожидаемые таблицы.

    Проверка написана на JS (textbook/tests_truth_table_parser.js) и
    запускается через node: иначе она жила бы вне единственного раннера
    проекта и не бежала бы никогда. Без node тест пропускается – на проде
    node нет, а тесты там гоняют.

    Первое выражение – функция задания 2; её таблица сверяется ещё и с
    seed_ege_theory_2._rows(), то есть с тем, что записано в статью. Так
    связаны все три счётчика: seed-команда, браузер и Python.
    """

    # Список подобран по граням приоритета: сравнения выше not, not выше and,
    # and выше or, цепочка сравнений разворачивается в and соседних пар.
    # Функция задания 2 берётся из seed-команды, а не переписывается сюда:
    # две копии одного выражения разошлись бы при первой же правке.
    EXPRESSIONS = [
        'x <= y',
        'y <= x',
        'x == y',
        'x != y',
        'not x or y',
        'x or y and z',
        'not x == y',
        'x <= y <= z',
        '(x or y) <= z',
        'x <= (y or z)',
        'not (x and y) or z',
        'x >= y',
        'x < y',
        'x and not y or z',
        'x == y == z',
        '(x or y) and (not (y and z))',
    ]

    @staticmethod
    def _table(src):
        """Таблица истинности выражения, посчитанная самим Python."""
        import re
        from itertools import product

        names = sorted(set(re.findall(r'\b[a-z]\b', src)))
        rows = []
        for values in product((False, True), repeat=len(names)):
            env = dict(zip(names, values))
            rows.append([int(v) for v in values] + [int(bool(eval(src, {'__builtins__': {}}, env)))])
        return rows

    def test_parser_matches_python(self):
        import json
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path

        node = shutil.which('node')
        if not node:
            self.skipTest('node не установлен')

        from textbook.management.commands.seed_ege_theory_2 import PY_EXPR, _rows

        cases = [{'src': src, 'rows': self._table(src)}
                 for src in [PY_EXPR] + self.EXPRESSIONS]
        self.assertEqual(
            cases[0]['rows'], _rows(),
            'питоновская запись в виджете разошлась с функцией из seed-команды',
        )

        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / 'cases.json'
            expected.write_text(json.dumps(cases), encoding='utf-8')
            result = subprocess.run(
                [node, 'textbook/tests_truth_table_parser.js', str(expected)],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class LinkRenderTests(SimpleTestCase):
    """Ссылка из текста урока: новая вкладка и защитный rel.

    Раньше target проставлялся только внешним ссылкам, а ссылка на соседний
    урок открывалась поверх страницы, которую ученик читает. Такая ссылка –
    справка «если подзабыли», уводить с неё не нужно.
    """

    def test_internal_link_opens_in_new_tab(self):
        html = markdownify('см. [урок](/textbook/article/3-2-bazovye-operatsii-ne-i-ili/)')
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn('href="/textbook/article/3-2-bazovye-operatsii-ne-i-ili/"', html)

    def test_external_link_still_opens_in_new_tab(self):
        html = markdownify('см. [ФИПИ](https://fipi.ru/)')
        self.assertIn('target="_blank"', html)
        self.assertIn('href="https://fipi.ru/"', html)


class ArticleFigureTests(SimpleTestCase):
    """Рисунок статьи – SVG в data-URI, и он обязан пережить санитайзер.

    Так сделаны все пять картинок разбора задания 15 (`_figure()` в
    seed_ege_theory_15.py). Схема держится на трёх мелочах в
    `textbook_tags.markdownify`, каждая из которых выглядит необязательной:
    `img` в списке тегов, `data` в списке протоколов и `div` с атрибутом
    `class`. Уберут любую – все картинки учебника молча исчезнут со страниц,
    ни одна другая проверка этого не заметит.
    """

    # Настоящий однопиксельный SVG, а не строка-заглушка: если протокол data
    # выкинут из белого списка, атрибут src срежется целиком.
    SVG_SRC = (
        'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjA'
        'wMC9zdmciIHZpZXdCb3g9IjAgMCAxIDEiLz4='
    )

    def _figure(self):
        return (
            f'<div class="ege-fig">'
            f'<img class="ege-fig__img ege-fig__img--light" alt="схема" src="{self.SVG_SRC}">'
            f'<img class="ege-fig__img ege-fig__img--dark" alt="схема" src="{self.SVG_SRC}">'
            f'</div>'
        )

    def test_data_uri_svg_survives_sanitizer(self):
        html = str(markdownify(f'Текст.\n\n{self._figure()}\n\nЕщё текст.'))
        self.assertIn(self.SVG_SRC, html)
        self.assertEqual(html.count('<img'), 2)

    def test_theme_classes_survive(self):
        """По этим классам CSS прячет картинку чужой темы."""
        html = str(markdownify(self._figure()))
        self.assertIn('ege-fig__img--light', html)
        self.assertIn('ege-fig__img--dark', html)

    def test_figure_is_not_wrapped_into_paragraph(self):
        """Обёртка должна остаться блочной.

        Попади она внутрь <p>, markdown применил бы к ней nl2br и разрезал
        картинку тегами <br> – ровно это происходит с inline-SVG.
        """
        html = str(markdownify(f'Текст.\n\n{self._figure()}'))
        self.assertNotIn('<p><div', html)
        self.assertNotIn('<br', html)


class WidgetMountTests(SimpleTestCase):
    """Виджеты статьи должны смонтироваться на своих же конфигах.

    `node --check` ловит только синтаксис: виджет с обращением к снесённой
    константе разбирается нормально, а падает при первом рендере. Браузер это
    прячет – TextbookWidgets.init() ловит исключение фабрики, и на странице
    остаётся пустая рамка с заголовком. Поэтому монтируем виджеты в node на
    заглушечном DOM (textbook/tests_widget_mount.js) и берём конфиги оттуда же,
    откуда их берёт база, – из seed-команды.

    Без node тест пропускается: на проде его нет, а тесты там гоняют.
    """

    def test_article_widgets_mount(self):
        import json
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path

        node = shutil.which('node')
        if not node:
            self.skipTest('node не установлен')

        from textbook.management.commands import seed_ege_theory_2 as ege2
        from textbook.management.commands import seed_ege_theory_4 as ege4
        from textbook.management.commands import seed_ege_theory_12 as ege12
        from textbook.management.commands import seed_textbook_block8 as block8

        configs = {
            # Разбор задания 4 ставит fano-code в урезанном виде: только
            # таблица кодов и дерево. Рядом – он же полный, иначе гейт
            # `minimal`, снёсший разметку всегда, прошёл бы незамеченным.
            'fano-code#minimal': {
                'minimal': True,
                'codes': (
                    [list(pair) for pair in ege4.KNOWN]
                    + [[sym, ''] for sym in ege4.UNKNOWN]
                ),
            },
            'fano-code#full': {
                'codes': [['А', '0'], ['Б', '10'], ['В', '110'], ['Г', '111']],
                'message': '0110100111',
            },
            'truth-steps': {
                'vars': list(ege2.VARS),
                'sets': [[s[v] for v in ege2.VARS] for s in ege2._zero_sets()],
                'fragF': 0,
                'steps': ege2._steps(),
            },
            # turing-machine – единственный здесь виджет, который сам
            # считает: остальные рисуют готовую трассу из seed-команды.
            # Поэтому его не только монтируем, но и догоняем до остановки
            # («До конца») – иначе ошибка в шаге ленты дожила бы до статьи,
            # где ответ разбора и ответ виджета разошлись бы молча.
            'turing-machine': {
                'alphabet': ege12.ALPHABET,
                'states': ege12.STATES,
                'program': {st: list(row) for st, row in ege12.PROGRAM.items()},
                'tape': format(ege12.NUMBER, 'b'),
                'head': 'right',
                'state': 'q0',
                '__click': ['До конца'],
            },
            # regex-lab – второй виджет, который считает сам: движок у него
            # браузерный, а диалект шаблонов питоновский, и расходятся они
            # ровно там, где в учебнике весь текст – на кириллице (`\w` и
            # `\b` в JS букву «к» буквой не считают). Поэтому сверяем не
            # разметку, а строку re.findall, которую виджет печатает, с
            # настоящим питоновским re на том же шаблоне и том же тексте.
            'regex-lab': {
                'pattern': block8.REGEX_LAB_PATTERN,
                'text': block8.REGEX_LAB_TEXT,
            },
            'regex-lab#date': {
                'pattern': block8.REGEX_DATE_PATTERN,
                'text': block8.REGEX_DATE_TEXT,
            },
            'regex-lab#groups': {
                'pattern': block8.REGEX_GROUP_PATTERN,
                'text': block8.REGEX_GROUP_TEXT,
            },
            'truth-table': {
                'vars': list(ege2.VARS),
                'code': ege2.PY_EXPR,
                'expr': ege2.FORMULA,
                'rows': ege2._rows(),
                'fragment': [list(r) for r in ege2.FRAGMENT],
                'filter': '0',
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'configs.json'
            path.write_text(json.dumps(configs), encoding='utf-8')
            result = subprocess.run(
                [node, 'textbook/tests_widget_mount.js', str(path)],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        drawn = {
            line.split(' ', 2)[1]: line.split(' ', 2)[2]
            for line in result.stdout.splitlines() if line.startswith('text ')
        }

        # Урезанный вид оставляет ровно две карточки. Гейты `minimal` в
        # textbook-widgets.js выглядят лишними («виджет же и так работает») и
        # первыми просятся под нож – без них в разборе задания 4 снова
        # появятся лента чужого сообщения, пресеты с готовым ответом и
        # кнопка, которой в условии букв не прибавить.
        for keep in ('Таблица кодов', 'Кодовое дерево'):
            self.assertIn(keep, drawn['fano-code#minimal'],
                          f'урезанный fano-code потерял «{keep}»')
        for gone in ('Лента битов', 'Собрать ленту', 'Условие Фано',
                     '+ добавить символ', 'Префиксный код'):
            self.assertNotIn(gone, drawn['fano-code#minimal'],
                             f'урезанный fano-code рисует «{gone}»')
            self.assertIn(gone, drawn['fano-code#full'],
                          f'полный fano-code потерял «{gone}» – гейт снёс разметку всем')

        # Лента после прогона обязана дать тот же ответ, что и разбор: число
        # в статье считает Python (_check в seed-команде), а на странице его
        # же показывает JS – две реализации одной машины Тьюринга.
        word, steps = ege12._run()
        self.assertIn(f'На ленте: {word}', drawn['turing-machine'])
        self.assertIn(f'В десятичной системе: {ege12.ANSWER}', drawn['turing-machine'])
        self.assertIn(f'шаг {steps} ', drawn['turing-machine'])

        # Виджет регулярных выражений обязан находить то же, что находит
        # python: строку re.findall он печатает сам, а здесь она считается
        # настоящим re. Разойтись они могут молча – на кириллице, на группах
        # (одна группа даёт строки, две – кортежи) и на пустых совпадениях.
        import re as _re

        def findall_line(pattern, text):
            found = _re.findall(pattern, text)
            shown = ', '.join(
                '(' + ', '.join(repr(g) for g in item) + ')' if isinstance(item, tuple)
                else repr(item)
                for item in found[:12]
            )
            tail = ', …' if len(found) > 12 else ''
            return f"re.findall(r'{pattern}', s) → [{shown}{tail}]"

        for name, pattern, text in (
            ('regex-lab', block8.REGEX_LAB_PATTERN, block8.REGEX_LAB_TEXT),
            ('regex-lab#date', block8.REGEX_DATE_PATTERN, block8.REGEX_DATE_TEXT),
            ('regex-lab#groups', block8.REGEX_GROUP_PATTERN, block8.REGEX_GROUP_TEXT),
        ):
            self.assertIn(findall_line(pattern, text), drawn[name],
                          f'{name}: браузерный движок нашёл не то, что python')

        # Кодовое дерево обязано расти вместе с текстом при показе с проектора.
        # present-mode.js масштабирует страницу корневым кеглем, поэтому SVG,
        # заданный пикселями, на стене оставался прежним рядом с выросшим
        # текстом. Размеры в rem выглядят придиркой – px тут «работает» –
        # и первыми просятся обратно.
        sizes = {
            line.split()[1]: line.split()[2:]
            for line in result.stdout.splitlines() if line.startswith('svg ')
        }
        for name in ('fano-code#minimal', 'fano-code#full'):
            for value in sizes[name]:
                self.assertTrue(value.endswith('rem'),
                                f'дерево {name} задано в «{value}» – на проекторе не вырастет')
