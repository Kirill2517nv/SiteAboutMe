"""План подготовки к ЕГЭ и повторение (quizzes/ege_plan.py)."""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from textbook.models import EgeTask

from . import ege_plan, ege_stats
from .ege_constants import EGE_CODE_TASKS, EGE_RECOMMENDED_TIME
from .models import EgePlan, PracticeItem, PracticeSession, Question, Quiz


def at(day, hour=12):
    return timezone.make_aware(datetime.combine(day, time(hour)))


class PresetTests(TestCase):
    def test_presets_are_permutations_with_linked_block(self):
        for key in ('easy', 'fast', 'paper'):
            order = ege_plan.preset_order(key)
            self.assertEqual(sorted(order), list(range(1, 28)), key)
            i = order.index(19)
            self.assertEqual(order[i:i + 3], [19, 20, 21], key)

    def test_easy_is_codifier(self):
        self.assertEqual(ege_plan.preset_order('easy'), list(range(1, 28)))

    def test_fast_goes_short_to_long(self):
        order = [n for n in ege_plan.preset_order('fast') if n not in (20, 21)]
        times = [EGE_RECOMMENDED_TIME[n] for n in order]
        self.assertEqual(times, sorted(times))

    def test_paper_puts_code_last(self):
        order = ege_plan.preset_order('paper')
        flags = [n in EGE_CODE_TASKS for n in order]
        self.assertEqual(flags, sorted(flags))

    def test_own_order_validated(self):
        self.assertIsNone(ege_plan.clean_order(['1', '2']))
        own = list(range(27, 0, -1))
        cleaned = ege_plan.clean_order([str(n) for n in own])
        i = cleaned.index(19)
        self.assertEqual(cleaned[i:i + 3], [19, 20, 21])


class SpreadTests(TestCase):
    def test_spread_keeps_count_and_order(self):
        order = list(range(1, 28))
        remaining = {n: 5 for n in order}
        weeks = ege_plan.spread(order, remaining, 20)
        self.assertEqual(len(weeks), 20)
        self.assertEqual(sum(sum(w.values()) for w in weeks), 135)
        # Номера подряд: первая неделя – начало порядка.
        self.assertIn(1, weeks[0])
        self.assertIn(27, weeks[-1])

    def test_weeks_balanced_by_minutes(self):
        order = list(range(1, 28))
        weeks = ege_plan.spread(order, {n: 5 for n in order}, 10)
        minutes = [sum(EGE_RECOMMENDED_TIME[n] * c for n, c in w.items()) for w in weeks]
        budget = sum(minutes) / 10
        # Неделя отличается от средней не больше, чем на самую долгую задачу.
        self.assertTrue(all(abs(m - budget) <= max(EGE_RECOMMENDED_TIME.values()) for m in minutes))


class ReviewLadderTests(TestCase):
    today = date(2026, 11, 19)

    def state(self, events):
        return ege_plan.review_state(events, self.today)

    def test_not_learned(self):
        self.assertIsNone(self.state([]))
        self.assertIsNone(self.state([(at(date(2026, 11, 1)), False, True)]))

    def test_ladder_two_three_four_cap(self):
        d = date(2026, 1, 5)
        events = [(at(d), True, False)]
        self.assertEqual(self.state(events)['interval'], 2)
        d += timedelta(weeks=2)
        events.append((at(d), True, True))
        self.assertEqual(self.state(events)['interval'], 3)
        d += timedelta(weeks=3)
        events.append((at(d), True, True))
        self.assertEqual(self.state(events)['interval'], 4)
        d += timedelta(weeks=5)
        events.append((at(d), True, True))
        self.assertEqual(self.state(events)['interval'], 4)

    def test_early_solve_only_restarts_clock(self):
        d = date(2026, 11, 1)
        state = self.state([(at(d), True, False), (at(d + timedelta(days=3)), True, False)])
        self.assertEqual(state['interval'], 2)
        self.assertEqual(state['due'], d + timedelta(days=3, weeks=2))

    def test_error_resets_to_one_week(self):
        d = date(2026, 10, 1)
        state = self.state([(at(d), True, False), (at(d + timedelta(weeks=2)), True, True),
                            (at(d + timedelta(weeks=5)), False, True)])
        self.assertEqual(state['interval'], 1)
        self.assertTrue(state['error'])
        self.assertEqual(state['due'], d + timedelta(weeks=6))
        # Верно через неделю – снова 2.
        state = self.state([(at(d), True, False), (at(d + timedelta(weeks=5)), False, True),
                            (at(d + timedelta(weeks=6)), True, True)])
        self.assertEqual(state['interval'], 2)
        self.assertFalse(state['error'])

    def test_due(self):
        state = self.state([(at(self.today - timedelta(weeks=2)), True, False)])
        self.assertTrue(state['is_due'])
        state = self.state([(at(self.today - timedelta(weeks=1)), True, False)])
        self.assertFalse(state['is_due'])


class PlanStatusTests(TestCase):
    """plan_status – чистая функция: план, моменты решений, банк, «сегодня»."""

    bank = {n: 30 for n in range(1, 28)}

    def plan(self, started, deadline, per_task=5):
        order = ege_plan.preset_order('easy')
        goal = ege_plan.targets(per_task, self.bank)
        baseline = ege_plan.make_baseline(order, goal, {}, started, deadline)
        baseline['start'] = 0
        return SimpleNamespace(per_task=per_task, order=order, started=started,
                               deadline=deadline, baseline=baseline)

    def test_quota_does_not_change_within_week(self):
        monday = date(2026, 11, 16)
        plan = self.plan(monday, date(2027, 4, 26))
        empty = ege_plan.plan_status(plan, {}, self.bank, monday, now=at(monday, 9))
        firsts = {1: [at(monday + timedelta(days=1))] * 3}
        later = ege_plan.plan_status(plan, firsts, self.bank, monday + timedelta(days=2),
                                     now=at(monday + timedelta(days=2)))
        self.assertEqual(empty['week_need'], later['week_need'])
        self.assertEqual(later['week_got'], min(3, empty['week'][0]['quota']))

    def test_missed_week_recalculated_and_lag_shown(self):
        monday = date(2026, 11, 2)
        plan = self.plan(monday, date(2027, 4, 26))
        first = ege_plan.plan_status(plan, {}, self.bank, monday, now=at(monday, 9))
        two_weeks = monday + timedelta(weeks=2)
        later = ege_plan.plan_status(plan, {}, self.bank, two_weeks, now=at(two_weeks, 9))
        self.assertGreater(later['week_need'], first['week_need'] - 1)
        self.assertGreater(later['lag'], 0)
        self.assertEqual(later['behind_weeks'], 2)
        self.assertEqual([h['state'] for h in later['history']], ['miss', 'miss'])

    def test_other_number_counts_in_plan_not_in_week(self):
        # Неделя велит решать №1, ученик решает №6: в общий план засчитано,
        # квота недели не закрыта, а в следующий понедельник №1 снова в квоте.
        monday = date(2026, 11, 9)
        plan = self.plan(monday, date(2027, 4, 26))
        first = ege_plan.plan_status(plan, {}, self.bank, monday, now=at(monday, 9))
        self.assertIn(1, [r['number'] for r in first['week']])
        firsts = {6: [at(monday + timedelta(days=1))] * 5}
        same = ege_plan.plan_status(plan, firsts, self.bank, monday + timedelta(days=2),
                                    now=at(monday + timedelta(days=2)))
        self.assertEqual(same['week_got'], 0)
        self.assertEqual(same['total_done'], 5)
        nxt = monday + timedelta(weeks=1)
        later = ege_plan.plan_status(plan, firsts, self.bank, nxt, now=at(nxt, 9))
        self.assertEqual(later['history'][0]['got'], 0)
        self.assertEqual(later['week'][0]['number'], 1)
        self.assertNotIn(6, [n for week in later['schedule'] for n, _ in week['items']])

    def test_done_capped_by_goal_and_bank(self):
        monday = date(2026, 11, 16)
        plan = self.plan(monday, date(2027, 4, 26))
        bank = {**self.bank, 2: 3}
        firsts = {1: [at(monday)] * 9, 2: [at(monday)] * 3}
        status = ege_plan.plan_status(plan, firsts, bank, monday, now=at(monday, 20))
        self.assertEqual(status['done'][1], 5)
        self.assertEqual(status['goal'][2], 3)
        self.assertEqual(status['done'][2], 3)

    def test_percent_counts_minutes(self):
        monday = date(2026, 11, 16)
        plan = self.plan(monday, date(2027, 4, 26))
        firsts = {1: [at(monday)] * 5}
        status = ege_plan.plan_status(plan, firsts, self.bank, monday, now=at(monday, 20))
        # 5 задач по 3 минуты из 135 задач плана на 1175 минут – чуть больше процента.
        self.assertEqual(status['percent'], round(15 / 1175 * 100))

    def test_forecast_counts_minutes_not_tasks(self):
        # Неделя за неделей – только короткие номера: в штуках темп высокий,
        # а по минутам план пройден на крохи, и прогноз уходит далеко за дедлайн.
        start = date(2026, 10, 5)
        today = date(2026, 11, 19)
        plan = self.plan(start, date(2027, 4, 26))
        firsts = {n: [at(start + timedelta(days=n))] * 5 for n in (1, 2, 3, 4, 10, 11, 13, 14, 15)}
        status = ege_plan.plan_status(plan, firsts, self.bank, today, now=at(today))
        tasks_pace = status['total_done'] / (((today - start).days + 1) / 7)
        by_tasks = today + timedelta(weeks=(status['total_goal'] - status['total_done']) / tasks_pace)
        self.assertGreater(status['forecast'], by_tasks)
        self.assertTrue(status['late_forecast'])

    def test_on_schedule_forecast_meets_deadline(self):
        # Ровно по графику, сегодня четверг с половиной недели: прогноз не позже дедлайна.
        start, deadline = date(2026, 9, 21), date(2027, 4, 26)
        today = date(2026, 11, 19)
        plan = self.plan(start, deadline)
        goal = ege_plan.targets(5, self.bank)
        firsts, week = {}, start
        while week < ege_plan.monday(today):
            quota, _ = ege_plan._week_quota(plan.order, goal, firsts, week, deadline)
            for n, count in quota[0].items():
                firsts.setdefault(n, []).extend([at(week)] * count)
            week += timedelta(weeks=1)
        quota, _ = ege_plan._week_quota(plan.order, goal, firsts, week, deadline)
        half = [n for n in plan.order for _ in range(quota[0].get(n, 0))]
        for n in half[:len(half) * 4 // 7]:
            firsts.setdefault(n, []).append(at(week))
        status = ege_plan.plan_status(plan, firsts, self.bank, today, now=at(today, 23))
        self.assertEqual(status['lag'], 0)
        self.assertFalse(status['late_forecast'], status['forecast'])

    def test_extra_shown_but_not_counted(self):
        monday = date(2026, 11, 16)
        plan = self.plan(monday, date(2027, 4, 26), per_task=7)
        firsts = {1: [at(monday)] * 10}
        status = ege_plan.plan_status(plan, firsts, self.bank, monday, now=at(monday, 20))
        row = next(r for r in status['by_number'] if r['number'] == 1)
        self.assertEqual((row['done'], row['goal'], row['extra']), (7, 7, 3))
        self.assertEqual((status['total_done'], status['total_extra']), (7, 3))

    def test_after_deadline_debt_stays(self):
        monday = date(2026, 11, 16)
        plan = self.plan(monday - timedelta(weeks=4), monday - timedelta(days=1))
        status = ege_plan.plan_status(plan, {}, self.bank, monday, now=at(monday, 9))
        self.assertTrue(status['overdue'])
        self.assertEqual(status['week_need'], status['total_goal'])


class ReviewBatchTests(TestCase):
    def test_batch_is_most_overdue_five(self):
        today = date(2026, 11, 19)
        events = {n: [(at(today - timedelta(weeks=2, days=n)), True, False)] for n in range(1, 13)}
        result = ege_plan.reviews(events, today)
        self.assertEqual(len(result['due']), 12)
        self.assertEqual(result['batch'], [12, 11, 10, 9, 8])
        self.assertEqual(result['more'], 7)


class PlanDbTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('planner', password='x')
        self.teacher = User.objects.create_superuser('teach', password='x')
        self.bank = Quiz.objects.create(title='Банк 1', quiz_type='bank', slug='plan-bank-1',
                                        is_public=True)
        self.questions = [
            Question.objects.create(quiz=self.bank, text=f'q{i}', question_type='text',
                                    correct_text_answer=str(i), ege_number=1)
            for i in range(6)
        ]
        EgeTask.objects.create(number=1, title='Задание 1')

    def solve(self, question, when=None, kind='topic', correct=True, attempts=1):
        session = PracticeSession.objects.create(user=self.user, kind=kind, mode='study')
        return PracticeItem.objects.create(
            session=session, question=question, is_correct=correct, attempts=attempts,
            answered_at=when or timezone.now())

    def test_plan_count_matches_task_card(self):
        for q in self.questions[:3]:
            self.solve(q)
        self.solve(self.questions[0])          # повтор той же задачи – не вторая
        ege_plan.save_plan(self.user, date.today() + timedelta(weeks=20), 5, 'easy')
        status = ege_plan.status(self.user)['plan']
        self.assertEqual(status['done'][1], ege_stats._solved_by_number(self.user)[1]['solved'])
        self.assertEqual(status['done'][1], 3)

    def test_review_needs_learned_number(self):
        self.client.force_login(self.user)
        resp = self.client.post('/ege/review/start/', {'numbers': '1'})
        self.assertEqual(resp.status_code, 403)
        self.solve(self.questions[0], when=timezone.now() - timedelta(weeks=3))
        resp = self.client.post('/ege/review/start/')
        self.assertEqual(resp.status_code, 302)
        session = PracticeSession.objects.get(user=self.user, kind='review')
        self.assertEqual(session.items.count(), 1)

    def test_review_error_and_second_try(self):
        self.solve(self.questions[0], when=timezone.now() - timedelta(weeks=3))
        self.solve(self.questions[1], kind='review', attempts=2)  # верно, но со второй
        reviews = ege_plan.status(self.user)['reviews']
        self.assertEqual(reviews['errors'], [1])
        self.assertEqual(reviews['learned'][0]['interval'], 1)

    def test_form_creates_plan_and_hub_shows_week(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/ege/plan/').status_code, 200)
        deadline = (date.today() + timedelta(weeks=10)).isoformat()
        resp = self.client.post('/ege/plan/', {'deadline': deadline, 'per_task': '4',
                                               'preset': 'fast'})
        self.assertEqual(resp.status_code, 302)
        plan = EgePlan.objects.get(user=self.user)
        self.assertEqual((plan.per_task, plan.preset), (4, 'fast'))
        self.assertEqual(plan.order, ege_plan.preset_order('fast'))
        hub = self.client.get('/ege/')
        self.assertContains(hub, 'Эта неделя')

    def test_form_defaults_are_set_and_labelled(self):
        self.client.force_login(self.user)
        resp = self.client.get('/ege/plan/')
        data = resp.context['form_json']
        self.assertIn('"preset": "fast"', data)
        self.assertIn('"perTask": 6', data)   # 7, но банк в тесте – 6 задач
        self.assertIn('-05-01"', data)
        self.assertContains(resp, 'по умолчанию – 7')
        self.assertContains(resp, 'От быстрых к долгим <span class="text-xs font-normal text-gray-400">· по умолчанию')

    def test_far_deadline_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post('/ege/plan/', {'deadline': '9999-12-31', 'per_task': '5',
                                               'preset': 'easy'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(EgePlan.objects.exists())

    def test_review_kind_not_startable_directly(self):
        self.client.force_login(self.user)
        self.client.post('/ege/practice/start/', {'kind': 'review', 'mode': 'study',
                                                  'ege_number': '1'})
        self.client.post('/ege/practice/start/', {'kind': 'check', 'mode': 'study',
                                                  'ege_number': '1'})
        self.assertFalse(PracticeSession.objects.filter(kind__in=('review', 'check')).exists())

    def test_review_session_pages_render(self):
        self.client.force_login(self.user)
        self.solve(self.questions[0], when=timezone.now() - timedelta(weeks=3))
        self.client.post('/ege/review/start/')
        session = PracticeSession.objects.get(user=self.user, kind='review')
        self.assertEqual(self.client.get(f'/ege/practice/{session.pk}/').status_code, 200)
        session.finished_at = timezone.now()
        session.save(update_fields=['finished_at'])
        self.assertEqual(self.client.get(f'/ege/practice/{session.pk}/result/').status_code, 200)

    def test_form_rejects_bad_input(self):
        self.client.force_login(self.user)
        resp = self.client.post('/ege/plan/', {'deadline': '2000-01-01', 'per_task': '1',
                                               'preset': 'own', 'order': '1,2'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(EgePlan.objects.exists())

    def test_teacher_edits_student_plan(self):
        self.client.force_login(self.teacher)
        deadline = (date.today() + timedelta(weeks=10)).isoformat()
        self.client.post(f'/ege/plan/?student={self.user.id}',
                         {'deadline': deadline, 'per_task': '3', 'preset': 'easy'})
        self.assertEqual(EgePlan.objects.get(user=self.user).per_task, 3)
        self.assertFalse(EgePlan.objects.filter(user=self.teacher).exists())

    def test_teacher_page_matches_student(self):
        self.solve(self.questions[0])
        ege_plan.save_plan(self.user, date.today() + timedelta(weeks=20), 5, 'easy')
        row = next(r for r in ege_plan.class_rows([self.user]))
        own = ege_plan.status(self.user)
        for key in ('total_done', 'total_goal', 'lag', 'week_need', 'week_got', 'percent'):
            self.assertEqual(row['plan'][key], own['plan'][key], key)
        self.assertEqual(row['reviews']['due'], own['reviews']['due'])

    def test_plans_page_alphabetical(self):
        User = get_user_model()
        for name in ('Яковлев', 'Ёлкин', 'Абрамов'):
            User.objects.create_user(name, password='x', last_name=name)
        self.client.force_login(self.teacher)
        html = self.client.get('/ege/plans/?group=all').content.decode()
        self.assertLess(html.index('Абрамов'), html.index('Ёлкин'))
        self.assertLess(html.index('Ёлкин'), html.index('Яковлев'))

    def test_plans_page_access(self):
        self.client.force_login(self.user)
        self.assertNotEqual(self.client.get('/ege/plans/').status_code, 200)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get('/ege/plans/?group=all').status_code, 200)

    def test_teacher_has_no_own_plan_but_sees_students(self):
        self.client.force_login(self.teacher)
        own = self.client.get('/ege/')
        self.assertNotContains(own, 'Эта неделя')
        self.assertNotContains(own, "tab = 'plan'")
        ege_plan.save_plan(self.user, date.today() + timedelta(weeks=20), 5, 'easy')
        other = self.client.get(f'/ege/?student={self.user.id}')
        self.assertContains(other, 'Эта неделя')
        self.assertContains(other, "tab = 'plan'")

    def test_guest_sees_demo_plan(self):
        resp = self.client.get('/ege/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Это пример плана')
