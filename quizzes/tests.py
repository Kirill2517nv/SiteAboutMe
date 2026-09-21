import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from . import ege_practice, ege_scoring, ege_stats
from .ege_constants import (
    EGE_MAX_PRIMARY, EGE_RECOMMENDED_TIME, EGE_TASK_POINTS, EXAM_MINUTES,
    MISTAKES_RED_AT, ege_mistakes_color, ege_score_color, ege_time_color,
    test_score_for,
)
from textbook.models import EgeTask
from textbook.templatetags.textbook_tags import plural

from .models import (
    CodeSubmission, ExamTaskProgress, PracticeItem, PracticeSession, Question,
    QuestionFile, Quiz, QuizAssignment, UserResult,
)
from .tasks import update_practice_item_from_submission as update_practice_from_submission
from .management.commands.load_ege import _create_test_cases, fix_empty_sub_markers
from .templatetags.ege_filters import render_question_text
from .utils import js_json


class EgeTimeColorTests(SimpleTestCase):
    """Пороги цвета времени общие для результатов варианта, отчёта и профиля."""

    def test_thresholds(self):
        # Задание 17: норма 13 минут (спецификация 2027), полторы нормы – 19,5.
        self.assertEqual(EGE_RECOMMENDED_TIME[17], 13)
        cases = {
            5 * 60: 'green',
            13 * 60: 'green',    # ровно норма – ещё зелёный
            14 * 60: 'yellow',
            19 * 60: 'yellow',   # полторы нормы ещё не пройдены
            20 * 60: 'red',
        }
        for seconds, expected in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(ege_time_color(seconds, 17), expected)

    def test_no_time_no_color(self):
        self.assertEqual(ege_time_color(0, 17), '')
        self.assertEqual(ege_time_color(None, 17), '')

    def test_unknown_number_falls_back_to_five_minutes(self):
        self.assertNotIn(99, EGE_RECOMMENDED_TIME)
        self.assertEqual(ege_time_color(4 * 60, 99), 'green')
        self.assertEqual(ege_time_color(9 * 60, 99), 'red')


class SessionSizeTests(TestCase):
    """
    Размер сессии считается от норматива, а не задан числом.

    TestCase, а не SimpleTestCase: размер экзамена сверяется со справочником
    заданий (EgeTask.exam_size), то есть ходит в базу даже без записей.

    Подробные границы обоих режимов проверяет SessionModeTests; здесь – общие
    свойства и то, что режим действительно переключает формулу.
    """

    def test_mode_switches_formula(self):
        # 45 минут в учёбе против часа с потолком в пять задач на экзамене.
        self.assertEqual(ege_practice.session_size(1, 'study'), 8)
        self.assertEqual(ege_practice.session_size(1, 'exam'), 5)
        self.assertEqual(ege_practice.session_size(27, 'study'), 1)
        self.assertEqual(ege_practice.session_size(27, 'exam'), 1)

    def test_study_is_default_mode(self):
        self.assertEqual(ege_practice.session_size(1), ege_practice.study_session_size(1))

    def test_unknown_number_uses_default_norm(self):
        # Неизвестный номер – пять минут: 45/5 = 9 в учёбе, но потолок 8;
        # на экзамене 60/5 = 12 упирается в свой потолок 5.
        self.assertEqual(ege_practice.session_size(99, 'study'), 8)
        self.assertEqual(ege_practice.session_size(99, 'exam'), 5)

    def test_never_zero(self):
        for number in range(1, 28):
            for mode in ('study', 'exam'):
                with self.subTest(number=number, mode=mode):
                    self.assertGreaterEqual(ege_practice.session_size(number, mode), 1)


class EffectiveDifficultyTests(SimpleTestCase):
    """
    Сложность: разметка импорта до накопления статистики, факт – после.

    Пороги дублируются в SQL-выражении ege_practice.effective_difficulty_expr(),
    поэтому границы проверяются явно.
    """

    def _q(self, difficulty, solve_rate):
        return Question(difficulty=difficulty, solve_rate=solve_rate)

    def test_no_stats_keeps_manual_value(self):
        self.assertEqual(self._q(3, None).effective_difficulty(), 3)

    def test_boundaries(self):
        cases = {0.9: 1, 0.7: 1, 0.69: 2, 0.4: 2, 0.39: 3, 0.0: 3}
        for rate, expected in cases.items():
            with self.subTest(rate=rate):
                # Ручное значение намеренно противоречит статистике: побеждать
                # должна статистика, иначе автокоррекция бессмысленна.
                self.assertEqual(self._q(1 if expected == 3 else 3, rate).effective_difficulty(), expected)


class ScoreConversionTests(SimpleTestCase):
    """Прогноз балла упирается в шкалу ЕГЭ, а не уходит выше ста."""

    def test_points_sum_to_max(self):
        self.assertEqual(sum(EGE_TASK_POINTS.values()), EGE_MAX_PRIMARY)
        self.assertEqual(EGE_MAX_PRIMARY, 29)

    def test_edges(self):
        self.assertEqual(test_score_for(0), 0)
        self.assertEqual(test_score_for(29), 100)
        self.assertEqual(test_score_for(40), 100)   # выше максимума – всё равно 100
        self.assertEqual(test_score_for(None), 0)


class QuestionSourceTests(SimpleTestCase):
    """Источник задачи из заголовка парсера."""

    def _source(self, title):
        from quizzes.templatetags.ege_filters import question_source
        return question_source(Question(title=title))

    def test_tail_after_dash(self):
        self.assertEqual(self._source('Задание 1 – ЕГКР 18.04.26'), 'ЕГКР 18.04.26')
        # Длинное тире в проекте вне закона, но в импорте оно встречается.
        self.assertEqual(self._source('Задание 17 — Основная волна 19.06.26'),
                         'Основная волна 19.06.26')

    def test_nothing_to_show(self):
        self.assertEqual(self._source('Задача 1'), '')
        self.assertEqual(self._source(''), '')


class PartialScoreTests(SimpleTestCase):
    """Шкала 0/1/2 в заданиях 26 и 27."""

    def _q(self, number, points=2):
        return Question(ege_number=number, points=points)

    def _grade(self, number, expected, got):
        from quizzes.ege_scoring import grade
        return grade(self._q(number), got, expected)

    def test_26_full_and_partial(self):
        exp = '2326 187'
        self.assertEqual(self._grade(26, exp, '2326 187'), 2)
        self.assertEqual(self._grade(26, exp, '187 2326'), 1)   # перепутаны местами
        self.assertEqual(self._grade(26, exp, '2326 999'), 1)   # верно одно число
        self.assertEqual(self._grade(26, exp, '2326'), 1)       # второго нет
        self.assertEqual(self._grade(26, exp, '1 2'), 0)

    def test_26_ignores_layout(self):
        # Пара через пробел и та же пара в две строки – один и тот же ответ.
        self.assertEqual(self._grade(26, '43656 36', '43656\n36'), 2)

    def test_27_full_and_partial(self):
        # С 2027 года ответ на 27-е – строка из двух чисел, правило то же, что у 26-го.
        exp = '539936 100704'
        self.assertEqual(self._grade(27, exp, '539936 100704'), 2)
        self.assertEqual(self._grade(27, exp, '100704 539936'), 1)  # перепутаны местами
        self.assertEqual(self._grade(27, exp, '539936 1'), 1)       # верно одно число
        self.assertEqual(self._grade(27, exp, '539936'), 1)         # второго нет
        self.assertEqual(self._grade(27, exp, '1 2'), 0)

    def test_27_old_format_falls_back_to_exact_match(self):
        # Задачи 27, импортированные до 2027 года: эталон из двух пар. Частичного
        # балла у них нет, но за точный ответ полный балл ставится по-прежнему.
        exp = '26216 24182\n150891 63754'
        self.assertEqual(self._grade(27, exp, exp), 2)
        self.assertEqual(self._grade(27, exp, '26216 24182\n1 2'), 0)

    def test_other_tasks_keep_binary_scoring(self):
        from quizzes.ege_scoring import grade
        self.assertIsNone(self._grade(17, '5 7', '7 5'))
        # Одного балла за задание мало для частичной шкалы.
        self.assertIsNone(grade(self._q(26, points=1), '1 2', '1 2'))


class OutputMatchTests(SimpleTestCase):
    """
    Сравнение вывода программы с эталоном.

    Числовой ответ проверяется по числам, а не по раскладке: у задания 20 ответ
    из двух чисел, и печатать их в строку или в столбик – дело программы.
    """

    def test_number_layout_does_not_matter(self):
        for output in ('98 293', '98\n293', '  98   293  \n', '98\n\n293\n'):
            with self.subTest(output=output):
                self.assertTrue(ege_scoring.outputs_match(output, '98 293'))

    def test_order_and_values_still_matter(self):
        self.assertFalse(ege_scoring.outputs_match('293 98', '98 293'))
        self.assertFalse(ege_scoring.outputs_match('98', '98 293'))
        self.assertFalse(ege_scoring.outputs_match('98 293 1', '98 293'))
        self.assertFalse(ege_scoring.outputs_match('', '98 293'))

    def test_non_numeric_output_is_compared_as_text(self):
        # Программа, печатающая лишнее, ответом не считается.
        self.assertFalse(ege_scoring.outputs_match('Ответ: 12', '12'))
        self.assertTrue(ege_scoring.outputs_match('ДА\nНЕТ', 'ДА\nНЕТ'))
        self.assertFalse(ege_scoring.outputs_match('ДА НЕТ', 'ДА\nНЕТ'))

    def test_negative_numbers(self):
        self.assertTrue(ege_scoring.outputs_match('-5\n7', '-5 7'))
        self.assertFalse(ege_scoring.outputs_match('5 7', '-5 7'))


class PartialScoreFlowTests(TestCase):
    """Частичный балл в сессии: задача не решена, но половина засчитана."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('half', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 26', quiz_type='bank',
                                        slug='bank-26', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='две ячейки', question_type='text',
            correct_text_answer='2326 187', ege_number=26, points=2,
        )
        self.session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='study', ege_number=26,
        )
        self.item = PracticeItem.objects.create(
            session=self.session, question=self.question, order=0,
        )
        self.client.force_login(self.user)

    def _answer(self, text):
        return self.client.post(
            f'/ege/practice/{self.session.pk}/answer/',
            data=json.dumps({'item_id': self.item.pk, 'answer': text}),
            content_type='application/json',
        )

    def test_swapped_numbers_give_one_point_but_not_a_solve(self):
        data = self._answer('187 2326').json()
        self.assertFalse(data['is_correct'])
        self.assertEqual(data['score'], 1)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_correct)
        self.assertEqual(self.item.score, 1)
        # Задача не закрыта: ученик может дорешать её на полный балл.
        self.assertFalse(self.item.is_locked)

    def test_partial_answer_stays_in_the_mistake_pool(self):
        self._answer('187 2326')
        self.assertEqual(ege_practice.mistake_count(self.user), 1)

    def test_partial_counts_as_half_in_statistics(self):
        self._answer('187 2326')
        row = ege_stats.mode_rows(self.user)[26]['study']
        self.assertEqual(row['attempted'], 1)
        self.assertEqual(row['correct'], 0.5)
        self.assertEqual(row['accuracy'], 50)

    def test_full_answer_scores_two(self):
        data = self._answer('2326 187').json()
        self.assertTrue(data['is_correct'])
        self.assertEqual(data['score'], 2)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_locked)


class VariantAttemptTests(TestCase):
    """
    Попытки по варианту: проверка кода тоже попытка.

    Раньше счётчик рос только на синхронной проверке текстового ответа, и задача
    на код, отправленная хоть десять раз, оставалась в прогрессе нетронутой –
    ни времени, ни попыток по варианту.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('examinee2', password='pwd')
        self.quiz = Quiz.objects.create(title='Вариант 2', quiz_type='exam',
                                        slug='var-2', is_public=True, exam_mode='practice')
        self.code = Question.objects.create(
            quiz=self.quiz, text='напишите программу', question_type='code',
            ege_number=17, points=1,
        )
        self.text = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='4', ege_number=1, points=1,
        )

    def _submit(self, is_correct):
        from quizzes.tasks import update_exam_progress_from_submission
        submission = CodeSubmission.objects.create(
            user=self.user, quiz=self.quiz, question=self.code,
            code='print(1)', status='failed', is_correct=is_correct,
        )
        update_exam_progress_from_submission(submission)
        return submission

    def _progress(self, question):
        return ExamTaskProgress.objects.get(
            user=self.user, quiz=self.quiz, question=question,
        )

    def test_failed_submission_counts_as_an_attempt(self):
        self._submit(False)
        self._submit(False)
        progress = self._progress(self.code)
        self.assertEqual(progress.attempts_to_solve, 2)
        self.assertFalse(progress.is_solved)

    def test_finish_counts_answered_task_once(self):
        self.client.force_login(self.user)
        self.client.post(
            f'/ege/{self.quiz.pk}/finish/',
            data=json.dumps({'answers': {str(self.text.pk): '5'}}),
            content_type='application/json',
        )
        self.assertEqual(self._progress(self.text).attempts_to_solve, 1)

    def test_counter_freezes_after_the_task_is_solved(self):
        # Две отправки до успеха – «решено со второй попытки». Дальнейшие
        # эксперименты с кодом счётчик не трогают.
        self._submit(False)
        self._submit(True)
        self._submit(False)
        self._submit(True)
        progress = self._progress(self.code)
        self.assertEqual(progress.attempts_to_solve, 2)
        self.assertTrue(progress.is_solved)

    def test_text_check_counts_every_try_until_solved(self):
        self.client.force_login(self.user)
        for answer in ('5', '6', '4', '4'):
            self.client.post(
                f'/ege/{self.quiz.pk}/check/',
                data=json.dumps({'question_id': self.text.pk, 'answer': answer}),
                content_type='application/json',
            )
        # Неверно, неверно, верно – три попытки; четвёртая проверка уже не в счёт.
        self.assertEqual(self._progress(self.text).attempts_to_solve, 3)

    def test_finish_does_not_add_to_existing_attempts(self):
        # Проверки кода уже посчитаны – завершение варианта не должно
        # добавлять к ним ещё одну.
        self._submit(False)
        self.client.force_login(self.user)
        self.client.post(
            f'/ege/{self.quiz.pk}/finish/',
            data=json.dumps({'answers': {str(self.code.pk): 'print(1)'}}),
            content_type='application/json',
        )
        self.assertEqual(self._progress(self.code).attempts_to_solve, 1)


class VariantSummaryTests(TestCase):
    """Свод по вариантам считается отдельно от статистики по задачам."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('variants', password='pwd')
        self.quiz = Quiz.objects.create(title='Вариант 1', quiz_type='exam',
                                        exam_mode='exam', slug='var-1', is_public=True)
        for points in (1, 2):
            Question.objects.create(
                quiz=self.quiz, text='задача', question_type='text',
                correct_text_answer='1', ege_number=1, points=points,
            )

    def _practice_variant(self):
        practice = Quiz.objects.create(title='Вариант 2 (тренировка)', quiz_type='exam',
                                       exam_mode='practice', slug='var-2', is_public=True)
        Question.objects.create(quiz=practice, text='задача', question_type='text',
                                correct_text_answer='1', ege_number=2, points=1)
        return practice

    def test_empty_until_the_first_attempt(self):
        summary = ege_stats.variant_summary(self.user)
        self.assertEqual(summary['exam']['total'], 1)
        self.assertEqual(summary['exam']['written'], 0)
        self.assertIsNone(summary['exam']['best_test'])
        # Цена варианта известна и до попытки – по ней рисуется шкала.
        self.assertEqual(summary['exam']['rows'][0].max_points, 3)

    def test_best_attempt_wins(self):
        for score in (1, 3):
            UserResult.objects.create(user=self.user, quiz=self.quiz, score=score)
        summary = ege_stats.variant_summary(self.user)['exam']
        self.assertEqual(summary['written'], 1)
        self.assertEqual(summary['attempts'], 2)
        self.assertEqual(summary['best_primary'], 3)
        self.assertEqual(summary['rows'][0].test_score,
                         ege_stats.test_score_for(3))

    def test_modes_are_counted_apart(self):
        # Тренировочный вариант виден в своей группе и никогда не смешивается
        # с экзаменационной: его решают с открытой теорией и без таймера.
        practice = self._practice_variant()
        UserResult.objects.create(user=self.user, quiz=practice, score=1)

        summary = ege_stats.variant_summary(self.user)
        self.assertEqual([row.title for row in summary['exam']['rows']], ['Вариант 1'])
        self.assertEqual(summary['exam']['written'], 0)
        self.assertEqual([row.title for row in summary['study']['rows']],
                         ['Вариант 2 (тренировка)'])
        self.assertEqual(summary['study']['written'], 1)
        self.assertEqual(summary['study']['best_primary'], 1)

    def test_practice_variant_never_reaches_the_forecast(self):
        # Балл тренировочного варианта не измеряет готовность: прогноз по нему
        # обещал бы результат, которого на настоящем экзамене не будет.
        practice = self._practice_variant()
        UserResult.objects.create(user=self.user, quiz=practice, score=1)

        self.assertFalse(ege_stats.variant_summary(self.user)['forecast']['has_data'])

    def test_forecast_takes_the_last_written_variant(self):
        # Первый вариант ученик писал, ещё не зная половины тем – в прогнозе
        # стоит последний результат, а не среднее и не лучший.
        UserResult.objects.create(user=self.user, quiz=self.quiz, score=3,
                                  duration=timedelta(minutes=200))
        UserResult.objects.create(user=self.user, quiz=self.quiz, score=1,
                                  duration=timedelta(minutes=250))

        forecast = ege_stats.variant_summary(self.user)['forecast']
        self.assertTrue(forecast['has_data'])
        self.assertEqual(forecast['primary'], 1)
        self.assertEqual(forecast['primary_max'], 3)   # цена этого варианта
        self.assertEqual(forecast['test'], ege_stats.test_score_for(1))
        self.assertEqual(forecast['minutes'], 250)
        self.assertEqual(forecast['over'], 250 - forecast['limit'])


class ScaleColorTests(SimpleTestCase):
    """
    Шкала «красный – зелёный» для крупных чисел на хабе.

    Ступеней пять, потому что Tailwind собирается заранее и класса под
    вычисленный на лету оттенок в CSS не будет. Проверяем концы шкалы, её
    середину и то, что счётчик ошибок идёт в обратную сторону.
    """

    def test_score_runs_from_red_to_green(self):
        self.assertEqual(ege_score_color(0), 'red')
        self.assertEqual(ege_score_color(50), 'amber')
        self.assertEqual(ege_score_color(100), 'emerald')
        # Выход за границы шкале не страшен: балл клипуется, а не индексируется.
        self.assertEqual(ege_score_color(None), 'red')
        self.assertEqual(ege_score_color(140), 'emerald')

    def test_mistakes_stay_red_and_only_get_denser(self):
        # Зелёного в долге по ошибкам нет: две задачи – бледно-красный,
        # тридцать – самый насыщенный.
        self.assertEqual(ege_mistakes_color(0), 'red1')
        self.assertEqual(ege_mistakes_color(2), 'red1')
        self.assertEqual(ege_mistakes_color(MISTAKES_RED_AT // 2), 'red3')
        self.assertEqual(ege_mistakes_color(MISTAKES_RED_AT), 'red5')
        self.assertEqual(ege_mistakes_color(MISTAKES_RED_AT * 2), 'red5')
        # Ступени только растут – ни одного отката назад по пути к порогу.
        steps = [ege_mistakes_color(n) for n in range(MISTAKES_RED_AT + 1)]
        self.assertEqual(steps, sorted(steps))


class PluralFilterTests(SimpleTestCase):
    """
    Русские окончания по числу.

    Встроенный pluralize на трёх формах молча отдаёт пустую строку – по всему
    проекту были «2 балл» и «3 блок». Фильтр закрывает именно этот случай,
    поэтому проверяем все три ветки и исключение на 11–19.
    """

    def test_three_forms(self):
        for value, expected in ((1, 'балл'), (2, 'балла'), (5, 'баллов'),
                                (11, 'баллов'), (21, 'балл'), (104, 'балла'),
                                (0, 'баллов')):
            self.assertEqual(f'балл{plural(value, ",а,ов")}', expected, value)

    def test_bad_input_is_silent(self):
        # В шаблоне падать нельзя: пустое окончание хуже неверного, но лучше 500.
        self.assertEqual(plural(None, ',а,ов'), '')
        self.assertEqual(plural(2, 'а,ов'), '')


class DemoOverviewTests(TestCase):
    """
    Пример прогресса для гостя: та же форма данных, что у настоящего свода.

    Форма важнее самих чисел: шаблон молча пропускает недостающий ключ, и
    разъехавшийся пример выглядел бы не ошибкой, а пустым блоком.
    """

    def test_shape_matches_the_real_overview(self):
        demo = ege_stats.demo_overview()
        real = ege_stats.overview(get_user_model().objects.create_user('real', password='x'))
        for key in ('score', 'weak', 'by_task', 'variants'):
            self.assertIn(key, demo)
        self.assertEqual(set(demo['score']), set(real['score']))
        self.assertEqual(set(demo['variants']['exam']), set(real['variants']['exam']))
        self.assertEqual(set(demo['variants']['forecast']),
                         set(ege_stats.variant_forecast(get_user_model()
                                                        .objects.get(username='real'))))

    def test_forecast_agrees_with_its_own_table(self):
        # Карточка прогноза и таблица под ней стоят на одной странице: если
        # балл не сходится с точностью по заданиям, пример перестаёт убеждать.
        demo = ege_stats.demo_overview()
        primary = sum(
            row['exam']['accuracy'] / 100 * ege_stats.EGE_TASK_POINTS[row['number']]
            for row in demo['by_task']['rows']
        )
        self.assertEqual(demo['score']['primary'], round(primary))
        self.assertEqual(demo['score']['covered'], 27)
        self.assertTrue(demo['score']['has_data'])
        self.assertTrue(demo['variants']['forecast']['has_data'])

    def test_demo_variants_have_no_database_id(self):
        # id=None – единственное, по чему шаблон отличает пример от строки БД
        # и не строит для неё ссылку на несуществующий вариант.
        demo = ege_stats.demo_overview()['variants']
        for mode in ('study', 'exam'):
            for row in demo[mode]['rows']:
                self.assertIsNone(row.id)

    def test_guest_sees_the_example_on_the_hub(self):
        response = self.client.get('/ege/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Это пример, а не ваши результаты')


class PracticePickTests(TestCase):
    """Отбор задач в сессию: нерешённые вперёд, фильтр сложности, пул ошибок."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('pupil', password='x')
        self.bank = Quiz.objects.create(title='Банк 17', quiz_type='bank', slug='t-bank-17')
        self.easy = Question.objects.create(
            quiz=self.bank, text='лёгкая', question_type='text',
            correct_text_answer='1', ege_number=17, difficulty=1,
        )
        self.hard = Question.objects.create(
            quiz=self.bank, text='трудная', question_type='text',
            correct_text_answer='2', ege_number=17, difficulty=3,
        )

    def _answer(self, question, is_correct):
        session = PracticeSession.objects.create(user=self.user, ege_number=17)
        return PracticeItem.objects.create(
            session=session, question=question, is_correct=is_correct,
            answered_at=timezone.now(),
        )

    def test_difficulty_filter(self):
        self.assertEqual(list(ege_practice.bank_queryset(17, 1)), [self.easy])
        self.assertEqual(list(ege_practice.bank_queryset(17, 3)), [self.hard])

    def test_solve_rate_overrides_manual_difficulty_in_filter(self):
        # Задача помечена «высокой», но решается почти всеми – в выборке
        # «высокая сложность» её быть не должно.
        self.hard.solve_rate = 0.95
        self.hard.save(update_fields=['solve_rate'])
        self.assertNotIn(self.hard, ege_practice.bank_queryset(17, 3))
        self.assertIn(self.hard, ege_practice.bank_queryset(17, 1))

    def test_solved_questions_go_last(self):
        self._answer(self.easy, True)
        picked = ege_practice.pick_topic_questions(self.user, 17, size=1)
        self.assertEqual(picked, [self.hard])

    def test_mistake_pool_tracks_last_outcome(self):
        self._answer(self.easy, False)
        self.assertEqual(ege_practice.mistake_count(self.user), 1)
        self.assertEqual(ege_practice.pick_mistake_questions(self.user), [self.easy])

        # Дорешал позже – долг закрыт, задача уходит из пула.
        self._answer(self.easy, True)
        self.assertEqual(ege_practice.mistake_count(self.user), 0)

    def test_mistake_session_takes_every_mistake(self):
        # Счётчик на кнопке и состав сессии – одно и то же число.
        for i in range(7):
            question = Question.objects.create(
                quiz=self.bank, text='задача %d' % i, question_type='text',
                correct_text_answer='1', ege_number=17,
            )
            self._answer(question, False)
        self.assertEqual(ege_practice.mistake_count(self.user), 7)
        session = ege_practice.build_session(self.user, kind='mistakes')
        self.assertEqual(session.items.count(), 7)

    def test_classroom_mistake_stays_out_of_pool(self):
        # Урок разбирается вместе с учителем – в долг ученика он не идёт.
        lesson = PracticeSession.objects.create(
            user=self.user, ege_number=17, kind='classroom',
        )
        PracticeItem.objects.create(
            session=lesson, question=self.easy, is_correct=False,
            answered_at=timezone.now(),
        )
        self.assertEqual(ege_practice.mistake_count(self.user), 0)

    def test_variant_questions_stay_out_of_practice(self):
        # Вариант и тренировка – разные наборы задач. Задача из собранного
        # варианта не выдаётся на тренировке, не идёт в долг по ошибкам и не
        # считается доступной, даже если номер задания тот же самый.
        variant = Quiz.objects.create(title='Вариант 1', quiz_type='exam', slug='t-var-1')
        from_variant = Question.objects.create(
            quiz=variant, text='из варианта', question_type='text',
            correct_text_answer='3', ege_number=17, difficulty=1,
        )
        self.assertNotIn(from_variant, ege_practice.bank_queryset(17))
        self.assertNotIn(from_variant, ege_practice.pick_topic_questions(self.user, 17))

        self._answer(from_variant, False)
        self.assertEqual(ege_practice.mistake_count(self.user), 0)
        self.assertEqual(ege_practice.pick_mistake_questions(self.user), [])

        counts = ege_practice.available_counts(17, self.user)
        self.assertEqual(counts['total'], 2)   # только две задачи банка

    def test_build_session_returns_none_when_bank_empty(self):
        self.assertIsNone(ege_practice.build_session(self.user, ege_number=3))

    def test_build_session_creates_items(self):
        session = ege_practice.build_session(self.user, ege_number=17, size=2)
        self.assertEqual(session.items.count(), 2)
        self.assertEqual(session.mode, 'study')


class EgeStatsTests(TestCase):
    """Метрики прогресса считаются по журналу тренировок."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('pupil2', password='x')
        self.bank = Quiz.objects.create(title='Банк 26', quiz_type='bank', slug='t-bank-26')
        self.session = PracticeSession.objects.create(user=self.user, ege_number=26)

    def _item(self, is_correct, seconds=60):
        question = Question.objects.create(
            quiz=self.bank, text='задача', question_type='text',
            correct_text_answer='1', ege_number=26, points=2,
        )
        return PracticeItem.objects.create(
            session=self.session, question=question, is_correct=is_correct,
            seconds=seconds, answered_at=timezone.now(),
        )

    def test_accuracy_counts_every_mode(self):
        self._item(True)
        self._item(True)
        self._item(False)
        self.assertAlmostEqual(ege_stats.task_accuracy(self.user)[26], 2 / 3)

    def test_card_counts_tasks_not_attempts(self):
        # Карточка обещает «решено X из Y задач банка», а не число попыток.
        solved_first = self._item(True)
        solved_first.attempts = 1
        solved_first.save(update_fields=['attempts'])

        solved_late = self._item(True)
        solved_late.attempts = 3
        solved_late.save(update_fields=['attempts'])

        self._item(False)          # четвёртая задача банка, ещё не решена
        self._item(None)

        card = [t for t in ege_stats.task_stats(self.user) if t['number'] == 26][0]
        self.assertEqual(card['bank_size'], 4)
        self.assertEqual(card['solved'], 2)
        self.assertEqual(card['first_try'], 1)
        self.assertEqual(card['progress'], 50)

    def test_same_task_solved_twice_counts_once(self):
        item = self._item(True)
        PracticeItem.objects.create(
            session=PracticeSession.objects.create(user=self.user, ege_number=26),
            question=item.question, is_correct=True, attempts=1,
            answered_at=timezone.now(),
        )
        card = [t for t in ege_stats.task_stats(self.user) if t['number'] == 26][0]
        self.assertEqual(card['solved'], 1)

    def test_variant_work_stays_off_the_card(self):
        # Задача из варианта не входит ни в банк, ни в «решено».
        variant = Quiz.objects.create(title='Вариант 9', quiz_type='exam', slug='t-var-9')
        question = Question.objects.create(
            quiz=variant, text='из варианта', question_type='text',
            correct_text_answer='1', ege_number=26, points=2,
        )
        ExamTaskProgress.objects.create(
            user=self.user, quiz=variant, question=question,
            is_solved=True, attempts_to_solve=1, time_spent_seconds=30,
        )
        card = [t for t in ege_stats.task_stats(self.user) if t['number'] == 26][0]
        self.assertEqual((card['bank_size'], card['solved'], card['attempted']), (0, 0, 0))

    def test_score_ignores_training(self):
        # Тренировка прогноза не даёт: на ней можно подсмотреть теорию.
        self._item(True)
        self._item(True)
        score = ege_stats.predicted_score(self.user)
        self.assertEqual(score['primary'], 0)
        self.assertEqual(score['covered'], 0)
        self.assertFalse(score['has_data'])

    def test_score_and_time_come_from_exams(self):
        exam = PracticeSession.objects.create(
            user=self.user, ege_number=26, mode='exam', finished_at=timezone.now(),
        )
        for is_correct in (True, True, False):
            question = Question.objects.create(
                quiz=self.bank, text='задача', question_type='text',
                correct_text_answer='1', ege_number=26, points=2,
            )
            PracticeItem.objects.create(
                session=exam, question=question, is_correct=is_correct,
                seconds=120, answered_at=timezone.now(),
            )

        score = ege_stats.predicted_score(self.user)
        # Задание 26 стоит 2 балла, точность 2/3 → 1.33 → 1 первичный балл.
        self.assertEqual(score['primary'], 1)
        self.assertEqual(score['covered'], 1)
        # Время – сумма средних по заданиям с экзаменом, остальные дают ноль.
        self.assertEqual(score['minutes'], 2)

    def test_anonymous_user_gets_empty_map(self):
        from django.contrib.auth.models import AnonymousUser
        stats = ege_stats.task_stats(AnonymousUser())
        self.assertEqual(len(stats), 27)
        self.assertTrue(all(item['accuracy'] is None for item in stats))


class CodifierChangeTests(TestCase):
    """
    Смена кодификатора: тема номера поменялась.

    Сценарий целиком: ученик решал старую тему задания 2, ФИПИ сменил её,
    старые задачи ушли в архив командой retag_ege, на тот же номер приехал
    новый банк. Проверяем, что после этого номер живёт новой темой, а история
    по старой не подмешивается в точность и прогноз балла.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('codifier', password='x')

        self.old_bank = Quiz.objects.create(
            title='Банк задание 2 (логика)', slug='old-bank-2',
            quiz_type='bank', exam_mode='practice', is_public=True,
        )
        self.old = [
            Question.objects.create(
                quiz=self.old_bank, title=f'Старая логика {i}',
                text='таблица истинности', question_type='text',
                correct_text_answer='1', ege_number=2, external_id=f'old-{i}',
            )
            for i in range(3)
        ]

        # Ученик решил все три задачи старой темы верно.
        session = PracticeSession.objects.create(user=self.user, ege_number=2)
        for i, question in enumerate(self.old):
            PracticeItem.objects.create(
                session=session, question=question, order=i,
                is_correct=True, seconds=30, answered_at=timezone.now(),
            )

    def _task2(self):
        # Кеш агрегации живёт на объекте user, в тесте он переиспользуется.
        if hasattr(self.user, '_ege_merged_cache'):
            del self.user._ege_merged_cache
        return {row['number']: row for row in ege_stats.task_stats(self.user)}[2]

    def _archive(self):
        from django.core.management import call_command
        call_command('retag_ege', '--from', '2', '--archive', verbosity=0)

    def test_before_change_old_theme_counts(self):
        stats = self._task2()
        self.assertEqual(stats['attempted'], 3)
        self.assertEqual(stats['accuracy'], 100)
        self.assertEqual(stats['bank_size'], 3)

    def test_archive_clears_number_for_new_theme(self):
        self._archive()
        stats = self._task2()
        # Номер обнулился: ни задач в банке, ни истории попыток.
        self.assertEqual(stats['bank_size'], 0)
        self.assertEqual(stats['attempted'], 0)
        self.assertIsNone(stats['accuracy'])

    def test_archived_questions_and_answers_survive(self):
        self._archive()
        self.assertEqual(Question.objects.filter(external_id__startswith='old-').count(), 3)
        self.assertEqual(
            PracticeItem.objects.filter(question__in=self.old, is_correct=True).count(), 3,
            'ответы учеников по архивным задачам должны сохраниться',
        )

    def test_new_theme_lands_on_same_number(self):
        self._archive()

        new_bank = Quiz.objects.create(
            title='Банк задание 2 (графы)', slug='new-bank-2',
            quiz_type='bank', exam_mode='practice', is_public=True,
        )
        fresh = [
            Question.objects.create(
                quiz=new_bank, title=f'Графы {i}', text='схема дорог',
                question_type='text', correct_text_answer='57',
                ege_number=2, external_id=f'new-{i}',
            )
            for i in range(4)
        ]

        # Тренировка по заданию 2 выдаёт только новые задачи.
        picked = ege_practice.pick_topic_questions(self.user, 2, size=10)
        self.assertTrue(picked)
        self.assertTrue(
            all(question.quiz_id == new_bank.id for question in picked),
            'в выдачу попала архивная задача старой темы',
        )

        # Ученик решает новую тему: одна верно, одна нет.
        session = PracticeSession.objects.create(user=self.user, ege_number=2)
        PracticeItem.objects.create(session=session, question=fresh[0], order=0,
                                    is_correct=True, seconds=40, answered_at=timezone.now())
        PracticeItem.objects.create(session=session, question=fresh[1], order=1,
                                    is_correct=False, seconds=50, answered_at=timezone.now())

        stats = self._task2()
        self.assertEqual(stats['bank_size'], 4)
        self.assertEqual(stats['attempted'], 2, 'старые попытки подмешались в новую тему')
        self.assertEqual(stats['correct'], 1)
        self.assertEqual(stats['accuracy'], 50)


class SessionModeTests(TestCase):
    """
    Учёба и экзамен: размеры, резерв и раздельный учёт.

    Размер учебной сессии считается от норматива без потолка, экзамен –
    фиксированная контрольная из резерва, состав которой ученик не выбирает.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('modes', password='x')
        self.bank = Quiz.objects.create(title='Банк 1', quiz_type='bank', slug='m-bank-1')
        self.pool = []      # резерв
        self.common = []    # обычные
        for i in range(12):
            question = Question.objects.create(
                quiz=self.bank, title=f'Задача {i}', text='условие',
                question_type='text', correct_text_answer=str(i),
                ege_number=1, difficulty=1, exam_only=(i < 5),
            )
            (self.pool if i < 5 else self.common).append(question)

    def test_study_size_norm_capped_at_default(self):
        # Норматив задаёт верхнюю границу, потолок в 8 задач – нижнюю:
        # 45/3 = 15 у задания 1 и 45/2 = 22 у задания 4 упираются в потолок,
        # а длинные задания остаются короче него.
        self.assertEqual(ege_practice.study_session_size(1), 8)
        self.assertEqual(ege_practice.study_session_size(4), 8)
        self.assertEqual(ege_practice.study_session_size(17), 3)   # 45/14 → 3
        self.assertEqual(ege_practice.study_session_size(27), 1)   # 45/40 → 1

    def test_study_size_never_exceeds_default_cap(self):
        from .ege_constants import EGE_RECOMMENDED_TIME, STUDY_DEFAULT_SIZE
        for number in EGE_RECOMMENDED_TIME:
            with self.subTest(number=number):
                self.assertLessEqual(ege_practice.study_session_size(number),
                                     STUDY_DEFAULT_SIZE)

    def test_exam_size_fits_one_hour_and_caps_at_five(self):
        self.assertEqual(ege_practice.exam_session_size(1), 5)    # 60/3=20, потолок 5
        self.assertEqual(ege_practice.exam_session_size(17), 4)   # 60/14=4.28 → 4
        self.assertEqual(ege_practice.exam_session_size(27), 1)   # 60/40=1.5 → 1

    def test_exam_size_override_from_admin(self):
        # Учитель ставит своё число в справочнике: по нормативу на задании 1
        # выходит пять, но если задачи номера тяжёлые, хватит и двух.
        EgeTask.objects.filter(number=1).delete()
        task = EgeTask.objects.create(number=1, title='Задание 1', exam_size=2)
        self.assertEqual(ege_practice.exam_session_size(1), 2)
        task.exam_size = None
        task.save(update_fields=['exam_size'])
        self.assertEqual(ege_practice.exam_session_size(1), 5)

    def test_exam_size_never_exceeds_hour(self):
        from .ege_constants import EGE_RECOMMENDED_TIME, EXAM_MINUTES
        for number, norm in EGE_RECOMMENDED_TIME.items():
            with self.subTest(number=number):
                spent = ege_practice.exam_session_size(number) * norm
                self.assertLessEqual(spent, EXAM_MINUTES)

    def test_reserve_hidden_from_study(self):
        picked = ege_practice.pick_topic_questions(self.user, 1, size=12)
        self.assertEqual(len(picked), 7, 'в учёбу попали резервные задачи')
        self.assertFalse(any(question.exam_only for question in picked))

    def test_reserve_excluded_from_form_counts(self):
        counts = ege_practice.available_counts(1)
        self.assertEqual(counts['total'], 7)
        self.assertEqual(ege_practice.exam_pool_size(1), 5)

    def test_exam_takes_reserve_first(self):
        session = ege_practice.build_session(self.user, ege_number=1, mode='exam')
        questions = [item.question for item in session.items.all()]
        self.assertEqual(len(questions), 5)
        self.assertTrue(all(question.exam_only for question in questions))

    def test_exam_ignores_requested_size_and_mix(self):
        # Состав контрольной ученик не выбирает – иначе «экзамен» из двух
        # базовых задач ничего бы не проверял.
        session = ege_practice.build_session(
            self.user, ege_number=1, mode='exam', size=99, mix={1: 2},
        )
        self.assertEqual(session.items.count(), 5)

    def test_second_exam_does_not_repeat_reserve(self):
        first = ege_practice.build_session(self.user, ege_number=1, mode='exam')
        for item in first.items.all():
            item.is_correct = True
            item.answered_at = timezone.now()
            item.save(update_fields=['is_correct', 'answered_at'])
        first.finished_at = timezone.now()
        first.save(update_fields=['finished_at'])

        second = ege_practice.build_session(self.user, ege_number=1, mode='exam')
        repeated = second.items.filter(question__exam_only=True).count()
        self.assertEqual(repeated, 0, 'повторный экзамен выдал те же резервные задачи')

    def test_mix_respects_requested_counts(self):
        for question in self.common[:3]:
            question.difficulty = 3
            question.save(update_fields=['difficulty'])

        session = ege_practice.build_session(self.user, ege_number=1, mix={1: 2, 3: 2})
        levels = sorted(item.question.effective_difficulty() for item in session.items.all())
        self.assertEqual(levels, [1, 1, 3, 3])

    def test_study_and_exam_counted_separately(self):
        # Учёба: одна верно, одна нет. Экзамен: обе верно.
        study = PracticeSession.objects.create(user=self.user, ege_number=1, mode='study')
        for question, ok in zip(self.common[:2], (True, False)):
            PracticeItem.objects.create(session=study, question=question,
                                        is_correct=ok, answered_at=timezone.now())

        exam = PracticeSession.objects.create(user=self.user, ege_number=1, mode='exam',
                                              finished_at=timezone.now())
        for question in self.pool[:2]:
            PracticeItem.objects.create(session=exam, question=question,
                                        is_correct=True, answered_at=timezone.now())

        if hasattr(self.user, '_ege_merged_cache'):
            del self.user._ege_merged_cache
        stats = {row['number']: row for row in ege_stats.task_stats(self.user)}[1]

        self.assertEqual(stats['study']['accuracy'], 50)
        self.assertEqual(stats['study']['sessions'], 1)
        self.assertEqual(stats['exam']['accuracy'], 100)
        self.assertEqual(stats['exam']['sessions'], 1)
        # Общая точность по-прежнему складывает оба режима.
        self.assertEqual(stats['attempted'], 4)

    def test_unfinished_exam_not_counted_as_passed(self):
        PracticeSession.objects.create(user=self.user, ege_number=1, mode='exam')
        stats = {row['number']: row for row in ege_stats.task_stats(self.user)}[1]
        self.assertEqual(stats['exam']['sessions'], 0,
                         'брошенный экзамен не должен считаться пройденным')


class PracticeAttemptTests(TestCase):
    """
    Учёба измеряет решение, а не переписывание ответа.

    До этих правил неверная попытка сразу показывала верный ответ, ученик
    вписывал его и задача уходила в статистику как решённая. Теперь ответ
    отдаёт только кнопка «Показать ответ», и она же закрывает задачу.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('practicer', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 1', quiz_type='bank',
                                        slug='bank-1', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='4', ege_number=1,
        )
        self.session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='study', ege_number=1,
        )
        self.item = PracticeItem.objects.create(
            session=self.session, question=self.question, order=0,
        )
        self.client.force_login(self.user)

    def _answer(self, text):
        return self.client.post(
            f'/ege/practice/{self.session.pk}/answer/',
            data=json.dumps({'item_id': self.item.pk, 'answer': text}),
            content_type='application/json',
        )

    def _reveal(self):
        return self.client.post(
            f'/ege/practice/{self.session.pk}/reveal/',
            data=json.dumps({'item_id': self.item.pk}),
            content_type='application/json',
        )

    def test_wrong_answer_hides_correct_one(self):
        data = self._answer('5').json()
        self.assertFalse(data['is_correct'])
        self.assertNotIn('correct_answer', data)

    def test_solved_on_second_attempt_counts_as_solved(self):
        self._answer('5')
        self._answer('4')
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_correct)
        self.assertEqual(self.item.attempts, 2)

    def test_solved_task_is_locked(self):
        self._answer('4')
        self.assertEqual(self._answer('5').status_code, 409)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_correct)
        self.assertEqual(self.item.attempts, 1)

    def test_reveal_gives_answer_and_fails_the_task(self):
        self._answer('5')
        data = self._reveal().json()
        self.assertEqual(data['correct_answer'], '4')
        self.item.refresh_from_db()
        self.assertTrue(self.item.gave_up)
        self.assertFalse(self.item.is_correct)
        # Верный ответ после сдачи задачу уже не спасает.
        self.assertEqual(self._answer('4').status_code, 409)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_correct)

    def test_reveal_refused_for_solved_task(self):
        self._answer('4')
        self.assertEqual(self._reveal().status_code, 409)

    def test_reveal_refused_on_exam(self):
        self.session.mode = 'exam'
        self.session.save(update_fields=['mode'])
        self.assertEqual(self._reveal().status_code, 403)

    # Рендер страницы: в тестах манифеста collectstatic нет, а ManifestStorage
    # из боевых настроек без него падает на первом же {% static %}.
    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_page_does_not_ship_correct_answers(self):
        # Ответ-маркер: искать по нему честнее, чем по имени поля – оно есть
        # в коде Alpine независимо от того, приехали данные или нет.
        self.question.correct_text_answer = 'ANSWERMARKER'
        self.question.save(update_fields=['correct_text_answer'])

        url = f'/ege/practice/{self.session.pk}/'
        self.assertNotIn('ANSWERMARKER', self.client.get(url).content.decode())

        self._reveal()
        # После сдачи ответ уже открыт – перезагрузка страницы его не прячет.
        self.assertIn('ANSWERMARKER', self.client.get(url).content.decode())


class ExamAnswerTests(TestCase):
    """
    На экзамене ответ сохраняется, но исход не сообщается ничем.

    Ни телом ответа на сохранение, ни данными страницы: иначе ученик узнавал бы
    результат по цвету кнопки в сетке задач сразу после перезагрузки.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('examinee', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 2', quiz_type='bank',
                                        slug='bank-2', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='4', ege_number=1,
        )
        self.session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='exam', ege_number=1,
        )
        self.item = PracticeItem.objects.create(
            session=self.session, question=self.question, order=0,
        )
        self.client.force_login(self.user)

    def _answer(self, text):
        return self.client.post(
            f'/ege/practice/{self.session.pk}/answer/',
            data=json.dumps({'item_id': self.item.pk, 'answer': text}),
            content_type='application/json',
        )

    def test_save_returns_no_verdict(self):
        data = self._answer('4').json()
        self.assertTrue(data['saved'])
        self.assertNotIn('is_correct', data)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_correct)   # в базе исход есть

    def test_answer_can_be_changed_until_finish(self):
        self._answer('4')
        self.assertEqual(self._answer('5').status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.text_answer, '5')
        self.assertFalse(self.item.is_correct)
        # Правки черновика попытками не считаются.
        self.assertEqual(self.item.attempts, 1)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_page_hides_outcome_after_reload(self):
        self._answer('4')
        html = self.client.get(f'/ege/practice/{self.session.pk}/').content.decode()
        payload = json.loads(re.search(r'items:\s*(\[.*?\]),\n', html, re.S).group(1))
        self.assertIsNone(payload[0]['is_correct'])
        self.assertFalse(payload[0]['locked'])
        self.assertEqual(payload[0]['answer'], '4')


class ExamExitTests(TestCase):
    """С экзамена не уйти: стрелки «назад» нет, а браузер спрашивает при уходе."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('locked', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 9', quiz_type='bank',
                                        slug='bank-9', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='4', ege_number=1,
        )
        self.client.force_login(self.user)

    def _page(self, mode):
        session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode=mode, ege_number=1,
        )
        PracticeItem.objects.create(session=session, question=self.question, order=0)
        return self.client.get(f'/ege/practice/{session.pk}/').content.decode()

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_exam_has_no_way_back(self):
        html = self._page('exam')
        self.assertNotIn('/ege/task/1/', html)
        self.assertIn('isExam: true', html)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_study_keeps_the_back_link(self):
        html = self._page('study')
        self.assertIn('/ege/task/1/', html)
        self.assertIn('isExam: false', html)


class ExamBeaconFinishTests(TestCase):
    """Уход с экзамена закрывает попытку и сохраняет недосланные ответы."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('leaver', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 10', quiz_type='bank',
                                        slug='bank-10', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='4', ege_number=1,
        )
        self.session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='exam', ege_number=1,
        )
        self.item = PracticeItem.objects.create(
            session=self.session, question=self.question, order=0,
        )
        self.client.force_login(self.user)

    def _beacon(self, answers):
        return self.client.post(
            f'/ege/practice/{self.session.pk}/finish/',
            data={'beacon': '1', 'answers': json.dumps(answers)},
        )

    def test_answer_saved_and_session_closed(self):
        resp = self._beacon([{'item_id': self.item.pk, 'answer': '4'}])
        self.assertEqual(resp.status_code, 204)   # маячок ответа не читает
        self.item.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(self.item.text_answer, '4')
        self.assertTrue(self.item.is_correct)
        self.assertIsNotNone(self.session.finished_at)

    def test_second_beacon_does_not_reopen_or_overwrite(self):
        self._beacon([{'item_id': self.item.pk, 'answer': '4'}])
        closed_at = PracticeSession.objects.get(pk=self.session.pk).finished_at
        self._beacon([{'item_id': self.item.pk, 'answer': '5'}])
        self.item.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(self.item.text_answer, '4')
        self.assertEqual(self.session.finished_at, closed_at)

    def test_foreign_session_is_refused(self):
        get_user_model().objects.create_user('stranger', password='pwd')
        self.client.force_login(get_user_model().objects.get(username='stranger'))
        self.assertEqual(self._beacon([]).status_code, 403)


class ExamSingleAttemptTests(TestCase):
    """Экзамен один за раз: вторая вкладка возвращает в уже идущую попытку."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('twotabs', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 11', quiz_type='bank',
                                        slug='bank-11', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='4', ege_number=1,
        )
        self.session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='exam', ege_number=1,
        )
        PracticeItem.objects.create(session=self.session, question=self.question, order=0)
        self.client.force_login(self.user)

    def _start_exam(self):
        return self.client.post('/ege/practice/start/',
                                {'kind': 'topic', 'mode': 'exam', 'ege_number': 1})

    def test_second_exam_redirects_to_the_running_one(self):
        resp = self._start_exam()
        self.assertRedirects(resp, f'/ege/practice/{self.session.pk}/',
                             fetch_redirect_response=False)
        self.assertEqual(PracticeSession.objects.filter(mode='exam').count(), 1)

    def test_expired_attempt_stops_blocking_and_gets_closed(self):
        PracticeSession.objects.filter(pk=self.session.pk).update(
            created_at=timezone.now() - timedelta(minutes=EXAM_MINUTES + 1),
        )
        self.assertIsNone(ege_practice.active_exam(self.user))
        self.session.refresh_from_db()
        self.assertEqual(self.session.finished_at, self.session.deadline)

    def test_study_session_is_not_blocked_by_a_running_exam(self):
        # Тренировка – не экзамен, её запуск ограничивать нечем.
        self.assertIsNotNone(
            ege_practice.build_session(self.user, ege_number=1, mode='study')
        )


class ExamDeadlineTests(TestCase):
    """
    Экзамен закрывается через час сам – и на сервере, а не только в браузере.

    Клиентский отсчёт можно остановить, закрыв вкладку; серверная проверка
    в _owned_session срабатывает при любом следующем обращении к сессии.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('timed', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 3', quiz_type='bank',
                                        slug='bank-3', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='4', ege_number=1,
        )
        self.session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='exam', ege_number=1,
        )
        self.item = PracticeItem.objects.create(
            session=self.session, question=self.question, order=0,
        )
        self.client.force_login(self.user)

    def _age(self, minutes):
        """Сдвигает начало сессии в прошлое (created_at – auto_now_add)."""
        started = timezone.now() - timedelta(minutes=minutes)
        PracticeSession.objects.filter(pk=self.session.pk).update(created_at=started)
        self.session.refresh_from_db()

    def test_deadline_is_one_hour_for_exam_only(self):
        self.assertEqual(self.session.deadline - self.session.created_at,
                         timedelta(minutes=EXAM_MINUTES))
        study = PracticeSession.objects.create(user=self.user, kind='topic', mode='study')
        self.assertIsNone(study.deadline)

    def test_expired_exam_closes_on_next_request(self):
        self._age(EXAM_MINUTES + 1)
        resp = self.client.get(f'/ege/practice/{self.session.pk}/')
        # Саму страницу разбора не тянем: в тестах нет манифеста collectstatic.
        self.assertRedirects(resp, f'/ege/practice/{self.session.pk}/result/',
                             fetch_redirect_response=False)
        self.session.refresh_from_db()
        # Закрыта моментом дедлайна, а не «сейчас»: забытая вкладка не должна
        # приносить в статистику лишние часы.
        self.assertEqual(self.session.finished_at, self.session.deadline)

    def test_expired_exam_rejects_answers(self):
        self._age(EXAM_MINUTES + 1)
        resp = self.client.post(
            f'/ege/practice/{self.session.pk}/answer/',
            data=json.dumps({'item_id': self.item.pk, 'answer': '4'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.is_correct)

    def test_running_exam_is_not_touched(self):
        self._age(30)
        self.assertFalse(self.session.is_expired)
        resp = self.client.post(
            f'/ege/practice/{self.session.pk}/answer/',
            data=json.dumps({'item_id': self.item.pk, 'answer': '4'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)


class ExamUnlockTests(TestCase):
    """
    Экзамен открывается только после работы в учёбе.

    Порог задаёт админ по каждому заданию: у короткого задания 1 десять задач –
    это разумная разминка, у задания 27 столько просто нет в банке.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('unlocker', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 4', quiz_type='bank',
                                        slug='bank-4', is_public=True)
        self.questions = [
            Question.objects.create(quiz=self.quiz, text=f'вопрос {i}',
                                    question_type='text', correct_text_answer=str(i),
                                    ege_number=1)
            for i in range(6)
        ]
        self.task = EgeTask.objects.create(number=1, title='Задание 1',
                                           exam_unlock_threshold=3)
        self.client.force_login(self.user)

    def _solve(self, count, mode='study'):
        session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode=mode, ege_number=1,
            finished_at=timezone.now(),
        )
        for i, question in enumerate(self.questions[:count]):
            PracticeItem.objects.create(session=session, question=question, order=i,
                                        is_correct=True, attempts=1,
                                        answered_at=timezone.now())
        return session

    def test_locked_until_threshold(self):
        self.assertEqual(ege_practice.exam_access(self.user, 1), (False, 0, 3))
        self._solve(2)
        self.assertEqual(ege_practice.exam_access(self.user, 1), (False, 2, 3))
        self._solve(3)
        self.assertEqual(ege_practice.exam_access(self.user, 1)[0], True)

    def test_same_question_solved_twice_counts_once(self):
        self._solve(1)
        self._solve(1)
        self.assertEqual(ege_practice.exam_access(self.user, 1)[1], 1)

    def test_zero_threshold_opens_immediately(self):
        self.task.exam_unlock_threshold = 0
        self.task.save(update_fields=['exam_unlock_threshold'])
        self.assertEqual(ege_practice.exam_access(self.user, 1), (True, 0, 0))

    def test_exam_start_refused_while_locked(self):
        resp = self.client.post('/ege/practice/start/', {
            'kind': 'topic', 'ege_number': '1', 'mode': 'exam',
        })
        self.assertRedirects(resp, '/ege/task/1/', fetch_redirect_response=False)
        self.assertFalse(PracticeSession.objects.filter(user=self.user, mode='exam').exists())

    def test_exam_progress_does_not_open_exam(self):
        # Экзаменационные решения порог не двигают: иначе первый же экзамен
        # открывал бы сам себя задним числом.
        self._solve(3, mode='exam')
        self.assertFalse(ege_practice.exam_access(self.user, 1)[0])


class QuestionGroupTests(TestCase):
    """
    Связки 19–21: условие игры описано в 19-м, 20-е и 21-е на него ссылаются.

    Разъединить их нельзя ни при каком отборе – ученик получит задачу про игру,
    которой не видел.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('gamer', password='x')
        self.bank = Quiz.objects.create(title='Банк 19-21', quiz_type='bank',
                                        slug='t-bank-19-21')
        self.groups = {}
        for gid in ('g-1', 'g-2'):
            self.groups[gid] = [
                Question.objects.create(
                    quiz=self.bank, text=f'{gid} задание {number}',
                    question_type='text', correct_text_answer='1',
                    ege_number=number, group_id=gid, group_order=order,
                )
                for order, number in enumerate((19, 20, 21))
            ]

    def _session(self, number):
        session = ege_practice.build_session(self.user, ege_number=number)
        return [item.question for item in session.items.select_related('question').order_by('order')]

    def test_session_serves_whole_group_in_order(self):
        for number in (19, 20, 21):
            with self.subTest(number=number):
                picked = self._session(number)
                # Задач всегда кратно трём, и внутри каждой тройки – 19, 20, 21.
                self.assertEqual(len(picked) % 3, 0)
                for start in range(0, len(picked), 3):
                    block = picked[start:start + 3]
                    self.assertEqual([q.ege_number for q in block], [19, 20, 21])
                    self.assertEqual(len({q.group_id for q in block}), 1)

    def test_solved_member_still_comes_with_the_group(self):
        # 19-е уже решено, но без него 20-е нерешаемо – выдаём снова.
        first = self.groups['g-1'][0]
        PracticeItem.objects.create(
            session=PracticeSession.objects.create(user=self.user, ege_number=19),
            question=first, is_correct=True, attempts=1, answered_at=timezone.now(),
        )
        for _ in range(5):
            picked = self._session(20)
            for start in range(0, len(picked), 3):
                self.assertEqual([q.ege_number for q in picked[start:start + 3]], [19, 20, 21])

    def test_ungrouped_questions_are_untouched(self):
        plain = Question.objects.create(
            quiz=self.bank, text='одиночка', question_type='text',
            correct_text_answer='1', ege_number=17,
        )
        self.assertEqual(ege_practice.expand_groups([plain]), [plain])

    def _answer(self, question, is_correct, answer='1'):
        session = PracticeSession.objects.create(user=self.user, ege_number=19)
        return PracticeItem.objects.create(
            session=session, question=question, is_correct=is_correct,
            text_answer=answer, attempts=1, answered_at=timezone.now(),
        )

    def test_solved_member_comes_prefilled_in_mistake_work(self):
        # Решил 19, ошибся в 20 и 21: в работе над ошибками правим только их,
        # а 19-е стоит рядом как условие игры с подставленным ответом.
        group = self.groups['g-1']
        self._answer(group[0], True, answer='42')
        self._answer(group[1], False)
        self._answer(group[2], False)

        work = ege_practice.build_session(self.user, kind='mistakes')
        rows = {i.question.ege_number: i for i in work.items.select_related('question')}
        self.assertTrue(rows[19].carried)
        self.assertEqual(rows[19].text_answer, '42')
        self.assertTrue(rows[19].is_correct)
        self.assertTrue(rows[19].is_locked)          # заново решать нечего
        self.assertFalse(rows[20].carried)
        self.assertFalse(rows[21].carried)

    def test_carried_answer_stays_out_of_statistics(self):
        group = self.groups['g-1']
        self._answer(group[0], True, answer='42')
        self._answer(group[1], False)
        before = [t for t in ege_stats.task_stats(self.user) if t['number'] == 19][0]

        ege_practice.build_session(self.user, kind='mistakes')
        after = [t for t in ege_stats.task_stats(self.user) if t['number'] == 19][0]
        self.assertEqual((before['attempted'], before['solved']),
                         (after['attempted'], after['solved']))
        # И задача не считается решённой второй раз в долге по ошибкам.
        self.assertEqual(ege_practice.mistake_count(self.user), 1)

    def test_mistake_session_keeps_every_mistake(self):
        # Связка не должна вытеснять реальные ошибки: счётчик на кнопке и
        # состав сессии обязаны сойтись.
        plain = [
            Question.objects.create(
                quiz=self.bank, text='одиночка %d' % i, question_type='text',
                correct_text_answer='1', ege_number=17,
            )
            for i in range(5)
        ]
        for question in plain:
            self._answer(question, False)
        self._answer(self.groups['g-1'][1], False)

        self.assertEqual(ege_practice.mistake_count(self.user), 6)
        work = ege_practice.build_session(self.user, kind='mistakes')
        numbers = [i.question.ege_number for i in work.items.select_related('question')]
        self.assertEqual(numbers.count(17), 5)
        self.assertEqual(sorted(n for n in numbers if n != 17), [19, 20, 21])

    def test_retry_keeps_the_group_together(self):
        # Задачи 19–21 решаются кодом, значит их можно переписать. Но и здесь
        # 20-е без условия игры из 19-го переписать нельзя.
        for question in self.groups['g-1']:
            question.question_type = 'code'
            question.save(update_fields=['question_type'])
            self._answer(question, True, answer='ответ %d' % question.ege_number)

        retry = ege_practice.build_retry_session(self.user, self.groups['g-1'][1])
        rows = {i.question.ege_number: i for i in retry.items.select_related('question')}
        self.assertEqual(sorted(rows), [19, 20, 21])
        self.assertFalse(rows[20].carried)       # её и переписываем
        self.assertTrue(rows[19].carried)
        self.assertEqual(rows[19].text_answer, 'ответ 19')
        self.assertTrue(rows[21].carried)

    def test_navigator_rows_split_mixed_session(self):
        from .views_practice import _navigator_rows

        plain = [
            Question.objects.create(
                quiz=self.bank, text='одиночка %d' % i, question_type='text',
                correct_text_answer='1', ege_number=17,
            )
            for i in range(5)
        ]
        session = PracticeSession.objects.create(user=self.user)
        for order, question in enumerate(self.groups['g-1'] + plain):
            PracticeItem.objects.create(session=session, question=question, order=order)

        rows = _navigator_rows(list(session.items.select_related('question').order_by('order')))
        self.assertEqual([(r['linked'], r['cells']) for r in rows],
                         [(True, [0, 1, 2]), (False, [3, 4, 5, 6]), (False, [7])])

    def test_form_size_means_groups(self):
        # Форма связанного задания спрашивает число троек: 2 в поле – 6 задач.
        self.assertEqual(ege_practice.group_span(20), 3)
        self.client.force_login(self.user)
        self.client.post('/ege/practice/start/', {
            'kind': 'topic', 'mode': 'study', 'ege_number': '20', 'size': '2',
        })
        session = PracticeSession.objects.filter(user=self.user).latest('id')
        numbers = [i.question.ege_number for i in session.items.select_related('question').order_by('order')]
        self.assertEqual(numbers, [19, 20, 21, 19, 20, 21])

    def test_group_span_is_one_without_groups(self):
        # У обычного задания множителя нет – размер остаётся числом задач.
        Question.objects.create(
            quiz=self.bank, text='одиночка', question_type='text',
            correct_text_answer='1', ege_number=17,
        )
        self.assertEqual(ege_practice.group_span(17), 1)

    def test_map_marks_the_linked_range(self):
        # Карта обводит связку рамкой: нужны границы и счёт в связках.
        cards = {t['number']: t for t in ege_stats.task_stats(self.user)}
        self.assertEqual(ege_stats.linked_numbers(), {19, 20, 21})
        self.assertTrue(cards[19]['linked_first'])
        self.assertTrue(cards[21]['linked_last'])
        for number in (19, 20, 21):
            self.assertTrue(cards[number]['linked'])
            self.assertEqual(cards[number]['groups'], 2)
        self.assertFalse(cards[17]['linked'])
        self.assertEqual(cards[17]['groups'], 0)

    def test_theory_badge_belongs_to_the_whole_group(self):
        # Разбор у связки один и лежит на 19-м номере, но читают его сразу за
        # три задания: плашка «теория» обязана стоять на всех трёх карточках,
        # а прочитанный разбор – считаться прочитанным у 20 и 21.
        from textbook.models import Article, ArticleProgress

        for number in (19, 20, 21):
            EgeTask.objects.get_or_create(
                number=number, defaults={'title': f'Задание {number}'})
        article = Article.objects.create(
            track='ege', slug='ege-19-teoriya-igr', title='Задания 19-21',
            ege_task=EgeTask.objects.get(number=19), is_published=True,
        )

        cards = {t['number']: t for t in ege_stats.task_stats(self.user)}
        for number in (19, 20, 21):
            self.assertEqual(cards[number]['theory']['total'], 1,
                             f'у задания {number} теория не показана')
            self.assertEqual(cards[number]['theory']['read'], 0)

        ArticleProgress.objects.create(user=self.user, article=article, status='read')
        cards = {t['number']: t for t in ege_stats.task_stats(self.user)}
        for number in (19, 20, 21):
            self.assertEqual(cards[number]['theory']['read'], 1,
                             f'прочитанный разбор не засчитан заданию {number}')
        # Чужому номеру связка ничего не отдаёт.
        self.assertEqual(cards[17]['theory']['total'], 0)

    def test_size_cuts_by_whole_groups(self):
        picked = ege_practice.expand_groups(
            [self.groups['g-1'][1], self.groups['g-2'][1]], size=4,
        )
        # Вторая связка целиком не влезает – берём только первую, а не полторы.
        self.assertEqual(len(picked), 3)
        self.assertEqual({q.group_id for q in picked}, {'g-1'})


class ClassroomPoolTests(TestCase):
    """
    Набор для урока одинаков у всех и не попадается на тренировках.

    Иначе разбирать задачу вместе невозможно: у каждого ученика под номером 1
    своя задача, а половина класса видела её дома.
    """

    def setUp(self):
        self.quiz = Quiz.objects.create(title='Банк 5', quiz_type='bank',
                                        slug='bank-5', is_public=True)
        self.classroom = [
            Question.objects.create(quiz=self.quiz, text=f'урок {i}',
                                    question_type='text', correct_text_answer='1',
                                    ege_number=2, classroom_only=True)
            for i in range(5)
        ]
        self.common = [
            Question.objects.create(quiz=self.quiz, text=f'обычная {i}',
                                    question_type='text', correct_text_answer='1',
                                    ege_number=2)
            for i in range(10)
        ]
        self.a = get_user_model().objects.create_user('pupil-a', password='pwd')
        self.b = get_user_model().objects.create_user('pupil-b', password='pwd')

    def test_same_set_and_order_for_everyone(self):
        first = ege_practice.pick_classroom_questions(2)
        second = ege_practice.pick_classroom_questions(2)
        self.assertEqual([q.id for q in first], [q.id for q in second])
        self.assertEqual(len(first), 5)

    def test_sessions_of_two_pupils_match(self):
        one = ege_practice.build_session(self.a, kind='classroom', ege_number=2)
        two = ege_practice.build_session(self.b, kind='classroom', ege_number=2)
        self.assertEqual(
            [i.question_id for i in one.items.order_by('order')],
            [i.question_id for i in two.items.order_by('order')],
        )
        # Урок идёт с разбором на месте.
        self.assertEqual(one.mode, 'study')

    def test_hidden_from_study_and_counts(self):
        picked = ege_practice.pick_topic_questions(self.a, 2, size=15)
        self.assertEqual(len(picked), 10)
        self.assertFalse([q for q in picked if q.classroom_only])
        self.assertEqual(ege_practice.available_counts(2)['total'], 10)

    def test_hidden_from_exam(self):
        chosen = ege_practice.pick_exam_questions(self.a, 2)
        self.assertFalse([q for q in chosen if q.classroom_only])


class LastExamStatsTests(TestCase):
    """Карточка задания показывает последнюю попытку, а не среднее по всем."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('repeater', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 6', quiz_type='bank',
                                        slug='bank-6', is_public=True)
        self.questions = [
            Question.objects.create(quiz=self.quiz, text=f'в {i}', question_type='text',
                                    correct_text_answer='1', ege_number=3)
            for i in range(2)
        ]

    def _exam(self, correct, minutes_ago):
        session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='exam', ege_number=3,
            finished_at=timezone.now() - timedelta(minutes=minutes_ago),
        )
        for i, question in enumerate(self.questions):
            PracticeItem.objects.create(
                session=session, question=question, order=i,
                is_correct=i < correct, attempts=1, answered_at=timezone.now(),
            )
        return session

    def test_last_attempt_wins(self):
        self._exam(correct=0, minutes_ago=60)    # первый блин
        self._exam(correct=2, minutes_ago=1)     # разобрался
        row = ege_stats.mode_rows(self.user)[3]['exam']
        self.assertEqual(row['last'], {'total': 2, 'correct': 2, 'accuracy': 100,
                                       'finished_at': row['last']['finished_at']})
        self.assertEqual(row['sessions'], 2)
        # Общая точность по всем экзаменам осталась прежней – она про другое.
        self.assertEqual(row['accuracy'], 50)

    def test_no_exams_gives_none(self):
        self.assertIsNone(ege_stats.mode_rows(self.user)[3]['exam']['last'])


class ClassroomToggleTests(TestCase):
    """Рубильник набора для урока доступен учителю прямо со страницы задания."""

    def setUp(self):
        self.teacher = get_user_model().objects.create_superuser('teacher', password='pwd')
        self.pupil = get_user_model().objects.create_user('pupil', password='pwd')
        self.task = EgeTask.objects.create(number=5, title='Задание 5')

    def test_teacher_toggles_both_ways(self):
        self.client.force_login(self.teacher)
        self.client.post('/ege/task/5/classroom/')
        self.task.refresh_from_db()
        self.assertTrue(self.task.classroom_enabled)

        self.client.post('/ege/task/5/classroom/')
        self.task.refresh_from_db()
        self.assertFalse(self.task.classroom_enabled)

    def test_pupil_cannot_toggle(self):
        self.client.force_login(self.pupil)
        resp = self.client.post('/ege/task/5/classroom/')
        self.assertEqual(resp.status_code, 403)
        self.task.refresh_from_db()
        self.assertFalse(self.task.classroom_enabled)

    def test_empty_pool_stays_closed_even_when_enabled(self):
        # Рубильник включён, но задач с галочкой нет – открывать нечего.
        self.task.classroom_enabled = True
        self.task.save(update_fields=['classroom_enabled'])
        self.assertFalse(ege_practice.classroom_open(5))


class NoRepeatTests(TestCase):
    """
    Решённую задачу второй раз не выдаём.

    Для текстовой задачи повтор бессмыслен – ответ уже известен, это ввод
    запомненного числа. Для задачи на код смысл есть: тот же алгоритм можно
    написать быстрее или экономнее, поэтому её ученик берёт сам из решённых.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('norepeat', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 7', quiz_type='bank',
                                        slug='bank-7', is_public=True)
        self.texts = [
            Question.objects.create(quiz=self.quiz, text=f'текст {i}', question_type='text',
                                    correct_text_answer=str(i), ege_number=7)
            for i in range(4)
        ]
        self.code = Question.objects.create(
            quiz=self.quiz, text='код', question_type='code', ege_number=7,
        )
        self.client.force_login(self.user)

    def _solve(self, question):
        session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='study', ege_number=7,
            finished_at=timezone.now(),
        )
        PracticeItem.objects.create(
            session=session, question=question, order=0, is_correct=True,
            attempts=1, answered_at=timezone.now(),
        )

    def test_solved_text_never_returns(self):
        self._solve(self.texts[0])
        for _ in range(5):
            picked = ege_practice.pick_topic_questions(self.user, 7, size=10)
            self.assertNotIn(self.texts[0].id, [q.id for q in picked])

    def test_solved_code_can_return(self):
        for question in self.texts:
            self._solve(question)
        self._solve(self.code)
        # Текстовые кончились, остаётся только решённая code-задача.
        picked = ege_practice.pick_topic_questions(self.user, 7, size=10)
        self.assertEqual([q.id for q in picked], [self.code.id])

    def test_counts_drop_as_tasks_are_solved(self):
        self.assertEqual(ege_practice.available_counts(7, self.user)['total'], 5)
        self._solve(self.texts[0])
        self.assertEqual(ege_practice.available_counts(7, self.user)['total'], 4)
        # Без ученика счётчик показывает весь банк.
        self.assertEqual(ege_practice.available_counts(7)['total'], 5)

    def test_everything_solved_gives_empty_session(self):
        for question in self.texts:
            self._solve(question)
        picked = ege_practice.pick_topic_questions(self.user, 7, size=10)
        self.assertEqual([q.id for q in picked], [self.code.id])

    def test_retry_only_for_code(self):
        self.assertIsNone(ege_practice.build_retry_session(self.user, self.texts[0]))
        session = ege_practice.build_retry_session(self.user, self.code)
        self.assertEqual([i.question_id for i in session.items.all()], [self.code.id])
        self.assertEqual(session.mode, 'study')

    def test_retry_view_refuses_text_question(self):
        resp = self.client.post(f'/ege/practice/retry/{self.texts[0].pk}/')
        self.assertEqual(resp.status_code, 403)

    def test_retry_view_starts_session_for_code(self):
        resp = self.client.post(f'/ege/practice/retry/{self.code.pk}/')
        session = PracticeSession.objects.filter(user=self.user).latest('created_at')
        self.assertRedirects(resp, f'/ege/practice/{session.pk}/',
                             fetch_redirect_response=False)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_solved_page_lists_own_solutions(self):
        self._solve(self.texts[0])
        html = self.client.get('/ege/task/7/solved/').content.decode()
        self.assertIn('Ваше решение', html)
        # Чужие решения на страницу не попадают.
        other = get_user_model().objects.create_user('other', password='pwd')
        session = PracticeSession.objects.create(user=other, kind='topic', mode='study',
                                                 ege_number=7)
        PracticeItem.objects.create(session=session, question=self.texts[1], order=0,
                                    is_correct=True, answered_at=timezone.now())
        html = self.client.get('/ege/task/7/solved/').content.decode()
        self.assertEqual(html.count('Ваше решение'), 1)


class RetrySessionTests(TestCase):
    """
    Переписывание решения улучшает показатели, но не пересматривает зачёт.

    Задача уже решена и посчитана. Второй заход – про качество кода: он может
    не пройти тесты, и это не повод объявить задачу нерешённой.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('optimizer', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 8', quiz_type='bank',
                                        slug='bank-8', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='напишите код', question_type='code', ege_number=17,
        )
        # Первое, засчитанное решение.
        self.first = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='study', ege_number=17,
            finished_at=timezone.now(),
        )
        PracticeItem.objects.create(
            session=self.first, question=self.question, order=0, is_correct=True,
            attempts=1, answered_at=timezone.now(),
            submission=self._submission(True, cpu=900, memory=5000),
        )

    def _submission(self, is_correct, cpu=None, memory=None):
        return CodeSubmission.objects.create(
            user=self.user, question=self.question, quiz=self.quiz,
            code='print(1)', status='success' if is_correct else 'failed',
            is_correct=is_correct, cpu_time_ms=cpu, memory_kb=memory,
        )

    def _retry_item(self):
        session = ege_practice.build_retry_session(self.user, self.question)
        return session, session.items.first()

    def test_failed_retry_keeps_task_solved(self):
        session, item = self._retry_item()
        update_practice_from_submission(self._submission(False))
        item.refresh_from_db()
        self.assertIsNone(item.is_correct)      # не «неверно», а «нет результата»
        self.assertEqual(item.attempts, 1)
        # Задача по-прежнему числится решённой и не вернётся в выборку.
        self.assertIn(self.question.id,
                      ege_practice._solved_question_ids(self.user, 17))

    def test_successful_retry_is_recorded(self):
        session, item = self._retry_item()
        better = self._submission(True, cpu=120, memory=3000)
        update_practice_from_submission(better)
        item.refresh_from_db()
        self.assertTrue(item.is_correct)
        self.assertEqual(item.submission_id, better.id)

    def test_retry_item_never_locks(self):
        session, item = self._retry_item()
        update_practice_from_submission(self._submission(True, cpu=100))
        item.refresh_from_db()
        # Замка нет: следующий вариант можно отправить сразу.
        self.assertFalse(item.is_locked)

    def test_retry_stays_out_of_statistics(self):
        before = ege_stats.mode_rows(self.user)[17]['study'].copy()
        session, item = self._retry_item()
        update_practice_from_submission(self._submission(True, cpu=100))
        if hasattr(self.user, '_ege_merged_cache'):
            del self.user._ege_merged_cache
        after = ege_stats.mode_rows(self.user)[17]['study']
        self.assertEqual((before['attempted'], before['correct'], before['sessions']),
                         (after['attempted'], after['correct'], after['sessions']))

    def test_best_metrics_may_come_from_different_attempts(self):
        # Быстрее, но прожорливее – и наоборот. Рекорды берутся раздельно.
        self._submission(True, cpu=100, memory=9000)
        self._submission(True, cpu=800, memory=1000)
        self._submission(False, cpu=1, memory=1)      # неверное не считается
        best = ege_practice.best_code_metrics(self.user, [self.question.id])
        self.assertEqual(best[self.question.id]['best_cpu'], 100)
        self.assertEqual(best[self.question.id]['best_memory'], 1000)
        self.assertEqual(best[self.question.id]['attempts'], 3)

    def test_retry_kind_cannot_be_requested_from_the_form(self):
        self.client.force_login(self.user)
        self.client.post('/ege/practice/start/', {
            'kind': 'retry', 'ege_number': '17', 'mode': 'study', 'size': '1',
        })
        self.assertFalse(
            PracticeSession.objects.filter(user=self.user, kind='retry').exists()
        )


class AdminPeekTests(TestCase):
    """
    Учитель видит верный ответ в любой сессии, ученик – нет.

    Панель рендерится на сервере: в JSON страницы ответы не попадают даже
    у суперпользователя, иначе разница между ролями держалась бы на том,
    открыл ли ученик инструменты разработчика.
    """

    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }

    def setUp(self):
        self.teacher = get_user_model().objects.create_superuser('peeker', password='pwd')
        self.pupil = get_user_model().objects.create_user('nopeek', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 9', quiz_type='bank',
                                        slug='bank-9', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='ANSWERMARKER', ege_number=9,
        )

    def _page(self, user, mode='study'):
        session = PracticeSession.objects.create(
            user=user, kind='topic', mode=mode, ege_number=9,
        )
        PracticeItem.objects.create(session=session, question=self.question, order=0)
        self.client.force_login(user)
        return self.client.get(f'/ege/practice/{session.pk}/').content.decode()

    @override_settings(STORAGES=STORAGES)
    def test_teacher_sees_answer_in_both_modes(self):
        for mode in ('study', 'exam'):
            with self.subTest(mode=mode):
                html = self._page(self.teacher, mode)
                self.assertIn('ANSWERMARKER', html)

    @override_settings(STORAGES=STORAGES)
    def test_pupil_sees_nothing(self):
        for mode in ('study', 'exam'):
            with self.subTest(mode=mode):
                html = self._page(self.pupil, mode)
                self.assertNotIn('ANSWERMARKER', html)

    @override_settings(STORAGES=STORAGES)
    def test_answer_is_not_in_page_data(self):
        html = self._page(self.teacher)
        payload = json.loads(
            re.search(r'items:\s*(\[.*?\]),\n', html, re.S).group(1))
        self.assertNotIn('correct_answer', payload[0])


class ModeTaskTableTests(TestCase):
    """
    Разбивка по заданиям и проекция «если бы вариант состоял из таких задач».

    Задания без личных замеров идут по нормативу ЕГЭ – иначе сумма времени
    у новичка была бы двадцать минут на весь вариант.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('projector', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 11', quiz_type='bank',
                                        slug='bank-11', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='в', question_type='text',
            correct_text_answer='1', ege_number=1,
        )
        EgeTask.objects.create(number=1, title='Задание 1')

    def _answer(self, mode, correct, seconds):
        session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode=mode, ege_number=1,
            finished_at=timezone.now(),
        )
        PracticeItem.objects.create(
            session=session, question=self.question, order=0, is_correct=correct,
            attempts=1, seconds=seconds, answered_at=timezone.now(),
        )

    def test_row_holds_both_modes(self):
        self._answer('study', True, 120)
        self._answer('exam', False, 60)
        table = ege_stats.mode_task_table(self.user)
        row = table['rows'][0]
        self.assertEqual(row['number'], 1)
        self.assertEqual(row['study']['avg_mm_ss'], '2:00')
        self.assertEqual(row['exam']['avg_mm_ss'], '1:00')
        self.assertEqual(row['study']['accuracy'], 100)
        self.assertEqual(row['exam']['accuracy'], 0)

    def test_untouched_tasks_are_not_listed(self):
        self._answer('study', True, 60)
        numbers = [row['number'] for row in ege_stats.mode_task_table(self.user)['rows']]
        self.assertEqual(numbers, [1])


class AverageTimeRuleTests(TestCase):
    """
    Среднее время считается по задачам с замером, а не по всем отвеченным.

    Задача, закрытая без единой замеренной секунды, среднее не разбавляет:
    то же правило стоит в _practice_rows, и расхождение между экранами ученик
    прочитал бы как ошибку в данных.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('timing', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 12', quiz_type='bank',
                                        slug='bank-12', is_public=True)
        self.questions = [
            Question.objects.create(quiz=self.quiz, text=f'в {i}', question_type='text',
                                    correct_text_answer='1', ege_number=13)
            for i in range(3)
        ]
        session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode='study', ege_number=13,
            finished_at=timezone.now(),
        )
        # Две задачи с замером и одна без него.
        for i, seconds in enumerate((60, 120, 0)):
            PracticeItem.objects.create(
                session=session, question=self.questions[i], order=i, is_correct=True,
                attempts=1, seconds=seconds, answered_at=timezone.now(),
            )

    def test_unmeasured_task_is_out_of_the_average(self):
        row = ege_stats.mode_rows(self.user)[13]['study']
        self.assertEqual(row['attempted'], 3)
        self.assertEqual(row['seconds_n'], 2)
        self.assertEqual(row['avg_seconds'], 90)          # 180 / 2, а не 180 / 3
        self.assertEqual(row['avg_mm_ss'], '1:30')

    def test_table_shows_the_same_average(self):
        row = ege_stats.mode_rows(self.user)[13]['study']
        table_row = ege_stats.mode_task_table(self.user)['rows'][0]
        self.assertEqual(table_row['study']['avg_mm_ss'], row['avg_mm_ss'])


class WeeklyDynamicsTests(TestCase):
    """
    Динамика разведена по источникам: тренировка, экзамен, готовый вариант.

    Общий столбик прятал бы, чем именно ученик занимался на неделе, а это
    разная работа: разминка, контрольная и полный вариант.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('weeks', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 13', quiz_type='bank',
                                        slug='bank-13', is_public=True)

    def _items(self, mode, correct, total):
        session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode=mode, ege_number=1,
            finished_at=timezone.now(),
        )
        for i in range(total):
            question = Question.objects.create(
                quiz=self.quiz, text=f'{mode} {i}', question_type='text',
                correct_text_answer='1', ege_number=1,
            )
            PracticeItem.objects.create(
                session=session, question=question, order=i, is_correct=i < correct,
                attempts=1, seconds=30, answered_at=timezone.now(),
            )

    def test_bars_split_by_source(self):
        self._items('study', correct=3, total=4)
        self._items('exam', correct=1, total=2)

        week = ege_stats.weekly_dynamics(self.user)[-1]
        bars = {bar['key']: bar for bar in week['bars']}
        self.assertEqual((bars['study']['correct'], bars['study']['attempted']), (3, 4))
        self.assertEqual((bars['exam']['correct'], bars['exam']['attempted']), (1, 2))
        self.assertEqual(bars['variant']['attempted'], 0)
        # Итог по неделе – сумма всех трёх.
        self.assertEqual((week['correct'], week['attempted']), (4, 6))

    def test_heights_share_one_scale(self):
        self._items('study', correct=4, total=4)
        self._items('exam', correct=1, total=2)
        bars = {bar['key']: bar for bar in ege_stats.weekly_dynamics(self.user)[-1]['bars']}
        # Пик – четыре задачи тренировки; экзамен вдвое ниже, а не тоже 100%.
        self.assertEqual(bars['study']['height_pct'], 100)
        self.assertEqual(bars['exam']['height_pct'], 50)

    def test_classroom_and_retry_stay_out(self):
        self._items('study', correct=1, total=1)
        for kind in ('classroom', 'retry'):
            session = PracticeSession.objects.create(
                user=self.user, kind=kind, mode='study', ege_number=1,
            )
            question = Question.objects.create(
                quiz=self.quiz, text=kind, question_type='text',
                correct_text_answer='1', ege_number=1,
            )
            PracticeItem.objects.create(
                session=session, question=question, order=0, is_correct=True,
                attempts=1, seconds=30, answered_at=timezone.now(),
            )
        week = ege_stats.weekly_dynamics(self.user)[-1]
        self.assertEqual(week['attempted'], 1)


class QuestionCheckViewTests(TestCase):
    """Проверка одного текстового ответа: вердикт есть, записи в БД нет."""

    def setUp(self):
        self.user = get_user_model().objects.create_user('checker', password='x')
        self.quiz = Quiz.objects.create(title='Практикум', is_public=True)
        QuizAssignment.objects.create(user=self.user, quiz=self.quiz)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2+2?', question_type='text', correct_text_answer='4',
        )
        self.url = f'/quizzes/question/{self.question.id}/check/'
        self.client.force_login(self.user)

    def _post(self, answer):
        return self.client.post(self.url, json.dumps({'answer': answer}),
                                content_type='application/json')

    def test_verdict_without_saving(self):
        self.assertJSONEqual(self._post(' 4 ').content, {'is_correct': True})
        self.assertJSONEqual(self._post('5').content, {'is_correct': False})
        # Балл ставит только finish_quiz_view – проверка ничего не записывает.
        self.assertFalse(UserResult.objects.filter(user=self.user).exists())

    def test_empty_answer_rejected(self):
        self.assertEqual(self._post('   ').status_code, 400)

    def test_code_question_rejected(self):
        code_q = Question.objects.create(quiz=self.quiz, text='код', question_type='code')
        resp = self.client.post(f'/quizzes/question/{code_q.id}/check/',
                                json.dumps({'answer': 'x'}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_foreign_quiz_forbidden(self):
        closed = Quiz.objects.create(title='Чужой', is_public=False)
        q = Question.objects.create(quiz=closed, text='?', question_type='text',
                                    correct_text_answer='4')
        resp = self.client.post(f'/quizzes/question/{q.id}/check/',
                                json.dumps({'answer': '4'}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)


class VariantByNumberTests(TestCase):
    """
    Плашка «По номерам заданий» на вкладке вариантов считает только варианты.

    Тренировка меряет разбор одной задачи с теорией под рукой, вариант – темп
    за 235 минут. Подмешанные тренировочные минуты покрасили бы номер не тем
    цветом, а решённые в тренажёре задачи – завысили бы «решено X из Y».
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('variant-time', password='pwd')
        self.variant = Quiz.objects.create(title='Вариант 7', quiz_type='exam',
                                           exam_mode='exam', slug='var-7', is_public=True)
        self.q1, self.q2 = [
            Question.objects.create(quiz=self.variant, text=f'в {i}', question_type='text',
                                    correct_text_answer='1', ege_number=1)
            for i in range(2)
        ]
        # Банк того же номера – в плашку он попасть не должен.
        bank = Quiz.objects.create(title='Банк 1', quiz_type='bank', slug='bank-1',
                                   is_public=True)
        bank_q = Question.objects.create(quiz=bank, text='банк', question_type='text',
                                         correct_text_answer='1', ege_number=1)
        session = PracticeSession.objects.create(user=self.user, kind='topic', mode='study',
                                                 ege_number=1, finished_at=timezone.now())
        PracticeItem.objects.create(session=session, question=bank_q, order=0,
                                    is_correct=True, attempts=1, seconds=600,
                                    answered_at=timezone.now())

    def _rows(self):
        return ege_stats.variant_summary(self.user)['by_number']

    def _row(self):
        return next(row for row in self._rows() if row['number'] == 1)

    def test_practice_does_not_leak_into_the_variant_row(self):
        # В тренажёре задача решена, в вариантах ученик к номеру не прикасался –
        # строки быть не должно вовсе, иначе тренировка выглядела бы работой
        # в варианте.
        self.assertEqual(self._rows(), [])

    def test_average_uses_only_measured_solved_tasks(self):
        ExamTaskProgress.objects.create(user=self.user, quiz=self.variant, question=self.q1,
                                        is_solved=True, time_spent_seconds=120)
        ExamTaskProgress.objects.create(user=self.user, quiz=self.variant, question=self.q2,
                                        is_solved=True, time_spent_seconds=0)
        row = self._row()['exam']
        self.assertEqual(row['total'], 2)           # две задачи варианта, банк не в счёт
        self.assertEqual(row['solved'], 2)
        self.assertEqual(row['avg_seconds'], 120)   # 120 / 1, а не 120 / 2
        self.assertEqual(row['avg_mm_ss'], '2:00')
        self.assertEqual(row['color'], 'green')     # цель по заданию 1 – 3 минуты

    def test_modes_keep_their_own_columns(self):
        # Один и тот же номер в тренировочном и экзаменационном варианте –
        # это две колонки одной строки, а не одно среднее: 20 минут разбора с
        # теорией под рукой не должны красить экзаменационный темп.
        practice = Quiz.objects.create(title='Вариант 8', quiz_type='exam',
                                       exam_mode='practice', slug='var-8', is_public=True)
        slow = Question.objects.create(quiz=practice, text='тренировочная',
                                       question_type='text', correct_text_answer='1',
                                       ege_number=1)
        ExamTaskProgress.objects.create(user=self.user, quiz=practice, question=slow,
                                        is_solved=True, time_spent_seconds=1200)
        ExamTaskProgress.objects.create(user=self.user, quiz=self.variant, question=self.q1,
                                        is_solved=True, time_spent_seconds=120)

        row = self._row()
        self.assertEqual(row['exam']['avg_seconds'], 120)
        self.assertEqual(row['exam']['color'], 'green')
        self.assertEqual(row['study']['avg_seconds'], 1200)
        self.assertEqual(row['study']['color'], 'red')

    def test_unsolved_task_still_gets_a_row(self):
        # Неверный ответ – тоже работа в варианте: строка нужна, иначе номер,
        # на котором ученик стабильно ошибается, просто исчезнет из таблицы.
        ExamTaskProgress.objects.create(user=self.user, quiz=self.variant, question=self.q1,
                                        is_solved=False, attempts_to_solve=2,
                                        time_spent_seconds=300)
        row = self._row()['exam']
        self.assertEqual(row['solved'], 0)
        self.assertEqual(row['total'], 2)
        self.assertEqual(row['avg_seconds'], 0)   # среднее – только по решённым
        self.assertEqual(row['color'], '')


class BankPoolViewTests(TestCase):
    """
    Страница банка: учитель читает условие и раскладывает задачи по наборам.

    Проверяем то, что нельзя увидеть глазами: чужого сюда не пускают,
    а связка 19–21 переезжает целиком, даже если тронули одну её задачу.
    """

    def setUp(self):
        User = get_user_model()
        self.teacher = User.objects.create_superuser('teacher', password='x')
        self.student = User.objects.create_user('pupil', password='x')
        self.bank = Quiz.objects.create(title='Банк 17', quiz_type='bank', slug='b-17')
        self.plain = Question.objects.create(
            quiz=self.bank, text='одиночка', question_type='text',
            correct_text_answer='1', ege_number=17,
        )
        self.group = [
            Question.objects.create(
                quiz=self.bank, text=f'связка {number}', question_type='text',
                correct_text_answer='1', ege_number=number,
                group_id='g-1', group_order=order,
            )
            for order, number in enumerate((19, 20, 21))
        ]

    def _post(self, number, data):
        self.client.force_login(self.teacher)
        return self.client.post(f'/ege/task/{number}/bank/', data)

    def test_student_is_not_allowed(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get('/ege/task/17/bank/').status_code, 403)

    def test_page_shows_hidden_pools_too(self):
        # Задача в резерве экзамена не выдаётся в тренировке, но учитель
        # должен видеть её здесь – иначе вернуть её обратно неоткуда.
        self.plain.exam_only = True
        self.plain.save(update_fields=['exam_only'])
        self.client.force_login(self.teacher)
        response = self.client.get('/ege/task/17/bank/')
        self.assertContains(response, 'одиночка')

    def test_pool_switch_saves(self):
        self._post(17, {f'pool_{self.plain.id}': 'classroom'})
        self.plain.refresh_from_db()
        self.assertTrue(self.plain.classroom_only)
        self.assertFalse(self.plain.exam_only)

        self._post(17, {f'pool_{self.plain.id}': 'study'})
        self.plain.refresh_from_db()
        self.assertFalse(self.plain.classroom_only)

    def test_group_moves_whole(self):
        # Тронули только 20-е; 19-е и 21-е обязаны уехать за ним, иначе
        # тренировка выдаст тройку без условия игры.
        data = {f'pool_{q.id}': 'study' for q in self.group}
        data[f'pool_{self.group[1].id}'] = 'classroom'
        self._post(19, data)
        for question in self.group:
            question.refresh_from_db()
            self.assertTrue(question.classroom_only, question.ege_number)


class ClassTableTests(TestCase):
    """
    Таблица класса и чужой прогресс: цифры те же, доступ – учительский.

    Главное здесь не вёрстка, а совпадение чисел. Таблица считается пачкой на
    весь класс (class_rows), личная вкладка – по одному ученику (predicted_score,
    mistake_count), и это два разных запроса к базе. Разойдись они – учитель
    увидел бы у ученика один балл в таблице и другой на его же странице.
    """

    def setUp(self):
        self.teacher = get_user_model().objects.create_superuser(
            'teacher', password='pwd')
        self.student = get_user_model().objects.create_user(
            'pupil', password='pwd', last_name='Иванов')
        self.quiz = Quiz.objects.create(title='Банк 17', quiz_type='bank',
                                        slug='bank-17', is_public=True)
        self.questions = [
            Question.objects.create(quiz=self.quiz, text=f'в{i}', question_type='text',
                                    correct_text_answer='1', ege_number=17)
            for i in range(3)
        ]
        EgeTask.objects.create(number=17, title='Задание 17')

    def _answer(self, question, mode, correct):
        session = PracticeSession.objects.create(
            user=self.student, kind='topic', mode=mode, ege_number=17,
            finished_at=timezone.now(),
        )
        PracticeItem.objects.create(
            session=session, question=question, order=0, is_correct=correct,
            attempts=1, seconds=60, answered_at=timezone.now(),
        )

    def _row(self):
        rows = ege_stats.class_rows([self.student])
        return rows[0]

    def test_forecast_matches_the_personal_page(self):
        self._answer(self.questions[0], 'exam', True)
        self._answer(self.questions[1], 'exam', False)
        self.assertEqual(self._row()['score']['test'],
                         ege_stats.predicted_score(self.student)['test'])

    def test_training_does_not_reach_the_forecast(self):
        # Тренировка идёт с открытой теорией – в прогнозе ей места нет.
        self._answer(self.questions[0], 'study', True)
        row = self._row()
        self.assertFalse(row['score']['has_data'])
        # Но в графике активности она видна: это работа, и она была.
        self.assertEqual(row['dynamics'][-1]['attempted'], 1)

    def test_mistakes_page_shows_the_same_tasks(self):
        # Счётчик в таблице ведёт на эту страницу – числа обязаны совпасть.
        self._answer(self.questions[0], 'study', False)
        self._answer(self.questions[1], 'study', False)
        self._answer(self.questions[2], 'study', True)
        self.client.login(username='teacher', password='pwd')
        response = self.client.get(f'/ege/student/{self.student.id}/mistakes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], self._row()['mistakes'])
        self.assertEqual([group['number'] for group in response.context['groups']], [17])

    def test_mistakes_page_is_closed_for_a_student(self):
        self.client.login(username='pupil', password='pwd')
        response = self.client.get(f'/ege/student/{self.student.id}/mistakes/')
        self.assertNotEqual(response.status_code, 200)

    def test_solved_task_is_not_listed_on_the_mistakes_page(self):
        self._answer(self.questions[0], 'study', False)
        self._answer(self.questions[0], 'study', True)
        self.client.login(username='teacher', password='pwd')
        response = self.client.get(f'/ege/student/{self.student.id}/mistakes/')
        self.assertEqual(response.context['total'], 0)

    def test_dynamics_share_one_scale_across_the_class(self):
        # Масштаб общий на класс: у того, кто решал вдвое меньше, и столбик вдвое
        # ниже. Свой масштаб на ученика нарисовал бы обоим одинаковые столбики.
        other = get_user_model().objects.create_user('pupil2', password='pwd')
        for question in self.questions:
            self._answer(question, 'study', True)
        session = PracticeSession.objects.create(
            user=other, kind='topic', mode='study', ege_number=17,
            finished_at=timezone.now(),
        )
        PracticeItem.objects.create(
            session=session, question=self.questions[0], order=0, is_correct=True,
            attempts=1, seconds=60, answered_at=timezone.now(),
        )
        rows = {row['user'].id: row for row in
                ege_stats.class_rows([self.student, other])}
        strong = rows[self.student.id]['dynamics'][-1]['bars'][0]
        weak = rows[other.id]['dynamics'][-1]['bars'][0]
        self.assertEqual(strong['height_pct'], 100)
        self.assertEqual(weak['height_pct'], 33)

    def test_mistakes_match_the_counter_on_the_hub(self):
        self._answer(self.questions[0], 'study', False)
        self._answer(self.questions[1], 'study', True)
        self.assertEqual(self._row()['mistakes'],
                         ege_practice.mistake_count(self.student))

    def test_solved_task_leaves_the_debt(self):
        # Побеждает последняя попытка: вчерашний провал сегодняшним решением закрыт.
        self._answer(self.questions[0], 'study', False)
        self._answer(self.questions[0], 'study', True)
        self.assertEqual(self._row()['mistakes'], 0)

    def test_weak_holds_only_attempted_tasks(self):
        self._answer(self.questions[0], 'study', False)
        weak = self._row()['weak']
        self.assertEqual([item['number'] for item in weak], [17])
        self.assertEqual(weak[0]['accuracy'], 0)

    def test_class_page_is_closed_for_a_student(self):
        self.client.login(username='pupil', password='pwd')
        self.assertNotEqual(self.client.get('/ege/class/').status_code, 200)

    def test_teacher_opens_the_class_page(self):
        self.client.login(username='teacher', password='pwd')
        self.assertEqual(self.client.get('/ege/class/?group=all').status_code, 200)

    def test_class_tab_filters_the_table(self):
        from accounts.models import Profile, StudentGroup
        group = StudentGroup.objects.create(name='9А')
        Profile.objects.update_or_create(user=self.student, defaults={'group': group})
        other = get_user_model().objects.create_user('pupil3', password='pwd')
        self.client.login(username='teacher', password='pwd')

        response = self.client.get(f'/ege/class/?group={group.id}')
        listed = [row['user'].id for row in response.context['rows']]
        self.assertIn(self.student.id, listed)
        self.assertNotIn(other.id, listed)

        # Без класса – своя вкладка: ученик, которого ещё никуда не записали,
        # не должен пропадать из таблицы совсем.
        response = self.client.get('/ege/class/?group=none')
        listed = [row['user'].id for row in response.context['rows']]
        self.assertIn(other.id, listed)
        self.assertNotIn(self.student.id, listed)

    def test_foreign_progress_is_closed_for_a_student(self):
        self.client.login(username='pupil', password='pwd')
        response = self.client.get(f'/ege/?student={self.teacher.id}')
        self.assertEqual(response.status_code, 403)

    def test_teacher_sees_the_student_numbers(self):
        self._answer(self.questions[0], 'study', False)
        self.client.login(username='teacher', password='pwd')
        response = self.client.get(f'/ege/?student={self.student.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['student'], self.student)
        self.assertEqual(response.context['overview']['mistakes'],
                         ege_practice.mistake_count(self.student))


class QuestionRenderTests(TestCase):
    """
    Условие задачи выглядит одинаково всюду, где его показывают.

    Два обещания, и оба легко сломать незаметно. Первое: банк учителя рисует
    задачу тем же партиалом, что и сессия ученика, – иначе вычитка банка ловит
    не то, что увидит ученик. Второе: формулы набираются на всех этих страницах,
    а не только на странице варианта, – пока конфиг MathJax был скопирован в
    четыре шаблона, сессии тренировки он просто не достался, и ученик читал
    «\\(F = \\neg x\\)» вместо формулы.
    """

    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }

    def setUp(self):
        self.teacher = get_user_model().objects.create_superuser('mathteacher', password='pwd')
        self.pupil = get_user_model().objects.create_user('mathpupil', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 9', quiz_type='bank',
                                        slug='bank-9', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text=r'Функция \(F = \neg x\) задана таблицей',
            question_type='text', correct_text_answer='1', ege_number=9,
        )
        self.solved_q = Question.objects.create(
            quiz=self.quiz, text='вторая', question_type='text',
            correct_text_answer='1', ege_number=9,
        )
        EgeTask.objects.create(number=9, title='Задание 9')

        # Одна задача решена, вторая провалена: страницам архива и разбора
        # ошибок нужно по строке, иначе они отрисуют пустое состояние.
        session = PracticeSession.objects.create(
            user=self.pupil, kind='topic', mode='study', ege_number=9)
        PracticeItem.objects.create(
            session=session, question=self.solved_q, order=0, is_correct=True,
            attempts=1, answered_at=timezone.now())
        PracticeItem.objects.create(
            session=session, question=self.question, order=1, is_correct=False,
            attempts=1, text_answer='2', answered_at=timezone.now())
        self.session = session

    @override_settings(STORAGES=STORAGES)
    def test_every_page_with_a_condition_loads_mathjax(self):
        self.client.force_login(self.teacher)
        pages = {
            'сессия': f'/ege/practice/{self.session.pk}/',
            'банк': '/ege/task/9/bank/',
            'решённые': '/ege/task/9/solved/',
            'ошибки': f'/ege/student/{self.pupil.id}/mistakes/',
        }
        for name, url in pages.items():
            with self.subTest(page=name):
                html = self.client.get(url).content.decode()
                self.assertIn('tex-chtml.js', html)
                # Конфиг ровно один: две копии на странице переопределяют
                # друг друга, и разделители начинают зависеть от порядка.
                self.assertEqual(html.count('window.MathJax'), 1)

    @override_settings(STORAGES=STORAGES)
    def test_teacher_panel_shows_the_expected_output(self):
        """
        У задачи на код ответ – это ожидаемый вывод теста, и учитель обязан его
        видеть. Проверка нужна именно шаблонная: неизвестный атрибут Django в
        шаблоне не считает ошибкой, он подставляет пустую строку, поэтому опечатка
        в имени поля выглядит как «у задачи нет ответа» и живёт годами.
        """
        from .models import TestCase as TestCaseModel

        code_q = Question.objects.create(
            quiz=self.quiz, text='напечатать ответ', question_type='code', ege_number=9)
        TestCaseModel.objects.create(question=code_q, input_data='', output_data='OUTPUTMARKER')

        session = PracticeSession.objects.create(
            user=self.teacher, kind='topic', mode='study', ege_number=9)
        PracticeItem.objects.create(session=session, question=code_q, order=0)
        mistake = PracticeSession.objects.create(
            user=self.pupil, kind='topic', mode='study', ege_number=9)
        PracticeItem.objects.create(
            session=mistake, question=code_q, order=0, is_correct=False,
            attempts=1, answered_at=timezone.now())

        self.client.force_login(self.teacher)
        pages = {
            'сессия': f'/ege/practice/{session.pk}/',
            'банк': '/ege/task/9/bank/',
            'ошибки': f'/ege/student/{self.pupil.id}/mistakes/',
        }
        for name, url in pages.items():
            with self.subTest(page=name):
                self.assertIn('OUTPUTMARKER', self.client.get(url).content.decode())

    @override_settings(STORAGES=STORAGES)
    def test_pupil_never_sees_the_expected_output(self):
        from .models import TestCase as TestCaseModel

        code_q = Question.objects.create(
            quiz=self.quiz, text='напечатать ответ', question_type='code', ege_number=9)
        TestCaseModel.objects.create(question=code_q, input_data='', output_data='OUTPUTMARKER')
        session = PracticeSession.objects.create(
            user=self.pupil, kind='topic', mode='study', ege_number=9)
        PracticeItem.objects.create(session=session, question=code_q, order=0)

        self.client.force_login(self.pupil)
        html = self.client.get(f'/ege/practice/{session.pk}/').content.decode()
        self.assertNotIn('OUTPUTMARKER', html)

    @override_settings(STORAGES=STORAGES)
    def test_bank_renders_the_condition_exactly_like_the_session(self):
        from django.template.loader import render_to_string

        fragment = render_to_string(
            'quizzes/_ege_question_body.html', {'question': self.question}).strip()
        self.client.force_login(self.teacher)
        for url in (f'/ege/practice/{self.session.pk}/', '/ege/task/9/bank/'):
            with self.subTest(url=url):
                self.assertIn(fragment, self.client.get(url).content.decode())
class QuestionTableRenderTests(SimpleTestCase):
    """
    Пустая ячейка в конце строки – это ячейка, а не конец таблицы.

    В задании 4 кодовое слово одного цвета нарочно пустое – его и ищет
    ученик. rstrip() срезал хвостовой таб, строка уезжала в абзац, и одна
    таблица превращалась в две с текстом посередине.
    """

    def test_trailing_tab_keeps_row_in_table(self):
        text = 'Цвет\tКод\nБелый\t0\nСиний\t\nЧёрный\t10'
        html = render_question_text(text)
        self.assertEqual(html.count('<table'), 1)
        self.assertEqual(html.count('<tr>'), 4)
        self.assertNotIn('<p', html)

    def test_empty_sub_marker_repaired_on_import(self):
        """
        Парсер отдаёт «q0[sub:]» вместо «q[sub:0]» – цифра снаружи, маркер
        пустой. Пустой маркер фильтр не ловит, и в таблице задания 12 ученик
        читал «q0[sub:]». Чиним на импорте, иначе следующий банк принесёт то же.
        """
        text = fix_empty_sub_markers('\ta0[sub:]\ta1[sub:]\nq0[sub:]\tкоманда\tкоманда')
        self.assertNotIn('[sub:]', text)
        html = render_question_text(text)
        self.assertIn('a<sub>0</sub>', html)
        self.assertIn('q<sub>0</sub>', html)


class TestCaseDedupeTests(TestCase):
    """
    Одинаковый кейс не заводится дважды.

    В заданиях 17 и 26 парсер отдаёт один и тот же ответ двумя кейсами – в
    строку и в столбик, – а раскладку чисел проверка и так не смотрит. Второй
    кейс не проверяет ничего, зато на каждой отправке поднимает ещё один
    контейнер и прогоняет решение по файлу данных заново.
    """

    def _load(self, cases):
        quiz = Quiz.objects.create(title='Банк 17', quiz_type='bank', slug='b17', is_public=True)
        q = Question.objects.create(quiz=quiz, text='условие', question_type='code', ege_number=17)
        _create_test_cases(q, {'test_cases': cases})
        return list(q.test_cases.all())

    def test_same_answer_in_another_layout_is_dropped(self):
        kept = self._load([
            {'input_data': '', 'output_data': '2508 104796'},
            {'input_data': '', 'output_data': '2508\n104796'},
        ])
        self.assertEqual([tc.output_data for tc in kept], ['2508 104796'])

    def test_different_answer_stays(self):
        kept = self._load([
            {'input_data': '', 'output_data': '2508 104796'},
            {'input_data': '', 'output_data': '104796 2508'},
            {'input_data': '5', 'output_data': '2508 104796'},
        ])
        self.assertEqual(len(kept), 3)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ResultPageLockTests(TestCase):
    """
    Разбор сессии закрыт, пока сессия идёт.

    Иначе экзамен обходился второй вкладкой: ответить наугад, открыть
    /result/, прочитать верный ответ (страница печатает его у неверных задач)
    и вернуться его вписать – ответы экзамена правятся до самого конца.
    В тренировке та же дыра выдавала бы ответ мимо «Показать ответ».
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user('peeker', password='pwd')
        self.quiz = Quiz.objects.create(title='Банк 26', quiz_type='bank',
                                        slug='bank-26', is_public=True)
        self.question = Question.objects.create(
            quiz=self.quiz, text='2 + 2', question_type='text',
            correct_text_answer='СЕКРЕТ42', ege_number=1,
        )
        self.client.force_login(self.user)

    def _session(self, mode):
        session = PracticeSession.objects.create(
            user=self.user, kind='topic', mode=mode, ege_number=1,
        )
        item = PracticeItem.objects.create(
            session=session, question=self.question, order=0,
        )
        self.client.post(
            f'/ege/practice/{session.pk}/answer/',
            data=json.dumps({'item_id': item.pk, 'answer': 'мимо'}),
            content_type='application/json',
        )
        return session

    def test_running_exam_result_redirects(self):
        session = self._session('exam')
        response = self.client.get(f'/ege/practice/{session.pk}/result/')
        self.assertRedirects(response, f'/ege/practice/{session.pk}/')

    def test_running_study_result_redirects(self):
        session = self._session('study')
        response = self.client.get(f'/ege/practice/{session.pk}/result/')
        self.assertRedirects(response, f'/ege/practice/{session.pk}/')

    def test_finished_session_shows_answer(self):
        session = self._session('exam')
        session.finished_at = timezone.now()
        session.save(update_fields=['finished_at'])
        html = self.client.get(
            f'/ege/practice/{session.pk}/result/'
        ).content.decode()
        self.assertIn('СЕКРЕТ42', html)


class JsJsonEscapeTests(SimpleTestCase):
    """
    Данные страницы уходят в сырой <script>, а пишет их ученик.

    В items_json попадает его ответ, в last_submissions_json – его код.
    json.dumps не трогает «<» и «>», поэтому «</script>» закрывал бы тег,
    и остаток строки становился разметкой на странице, которую открывает
    учитель под своей учётной записью.
    """

    def test_script_tag_cannot_escape(self):
        payload = js_json({'code': '</script><img src=x onerror=alert(1)>'})
        self.assertNotIn('<', payload)
        self.assertNotIn('>', payload)
        self.assertEqual(
            json.loads(payload)['code'],
            '</script><img src=x onerror=alert(1)>',
        )

    def test_plain_text_survives(self):
        self.assertEqual(json.loads(js_json({'a': 'ответ 42'}))['a'], 'ответ 42')


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ClassTableGroupFilterTests(TestCase):
    """?group= приходит из адреса – нечисловой мусор не должен ронять страницу."""

    def setUp(self):
        self.teacher = get_user_model().objects.create_superuser(
            'teacher-groups', 'teacher-groups@example.com', 'pwd',
        )
        self.client.force_login(self.teacher)

    def test_garbage_group_falls_back_to_all(self):
        response = self.client.get('/ege/class/?group=; DROP TABLE')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_group'], 'all')


class SandboxLimitsTests(SimpleTestCase):
    """Ограничения контейнера с кодом ученика.

    Проверено пробой изнутри контейнера: без cap_drop у кода дефолтный набор
    capabilities и uid 0, без pids_limit форк-бомба выедает таблицу процессов
    сервера, а не контейнера, без RLIMIT_FSIZE цикл записи забивает диск. Всё
    это – одна строка в словаре, которую легко потерять при правке, а увидеть
    пропажу можно только заглянув внутрь работающей песочницы.
    """

    def test_container_limits_are_set(self):
        from .utils import (
            CONTAINER_SECURITY, CONTAINER_WORKDIR, CONTAINER_FSIZE_LIMIT, RUNNER_PY,
        )

        self.assertTrue(CONTAINER_SECURITY['network_disabled'])
        self.assertEqual(CONTAINER_SECURITY['user'], 'nobody')
        self.assertEqual(CONTAINER_SECURITY['cap_drop'], ['ALL'])
        self.assertIn('no-new-privileges', CONTAINER_SECURITY['security_opt'])
        self.assertGreater(CONTAINER_SECURITY['pids_limit'], 0)
        # Каталог, созданный ключом working_dir, принадлежит root с правами
        # 755 – nobody не создаст в нём файл. Права 1777 есть только у /tmp.
        self.assertEqual(CONTAINER_WORKDIR, '/tmp')
        # Число в раннер подставляется заменой – шаблон не должен остаться.
        self.assertIn(f'({CONTAINER_FSIZE_LIMIT}, {CONTAINER_FSIZE_LIMIT})', RUNNER_PY)


class QuestionFileDownloadTests(TestCase):
    """Запись о файле переживает сам файл: seed-команды учебника сносят старый
    файл из хранилища, чтобы имя не разъехалось с условием задачи."""

    def test_missing_file_gives_404(self):
        user = get_user_model().objects.create_user('file-student', 'f@example.com', 'pwd')
        self.client.force_login(user)
        quiz = Quiz.objects.create(title='Практикум', slug='praktikum-files')
        question = Question.objects.create(
            quiz=quiz, question_type='code', text='Прочитайте файл',
        )
        ghost = QuestionFile.objects.create(
            question=question, file='question_files/ghost-never-written.txt',
        )
        response = self.client.get(f'/quizzes/question-file/{ghost.id}/download/')
        self.assertEqual(response.status_code, 404)
