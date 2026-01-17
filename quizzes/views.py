from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Max, Count
from .models import Quiz, Choice, UserResult, UserAnswer, TestCase
from accounts.models import StudentGroup
import datetime
import os
import json
from .utils import run_code_in_docker

def normalize_output(text):
    if not text:
        return ""
    lines = text.strip().splitlines()
    return "\n".join([line.rstrip() for line in lines])

def quiz_list_view(request):
    quizzes = Quiz.objects.all()
    
    # Оптимизация: загружаем все попытки пользователя одним запросом
    attempts_dict = {}
    if request.user.is_authenticated:
        attempts = UserResult.objects.filter(user=request.user).values('quiz_id').annotate(
            count=Count('id')
        )
        attempts_dict = {item['quiz_id']: item['count'] for item in attempts}
    
    quizzes_with_attempts = []
    now = timezone.now()
    
    for quiz in quizzes:
        attempts_count = attempts_dict.get(quiz.id, 0)
        is_blocked = False
        remaining_attempts = None
        status_message = None 
        
        is_open_by_date = True
        
        if quiz.start_date and now < quiz.start_date:
            is_open_by_date = False
            is_blocked = True
            status_message = f"Откроется: {quiz.start_date.strftime('%d.%m.%Y %H:%M')}"
        
        elif quiz.end_date and now > quiz.end_date:
            is_open_by_date = False
            is_blocked = True
            status_message = f"Завершился: {quiz.end_date.strftime('%d.%m.%Y %H:%M')}"

        if request.user.is_authenticated and quiz.max_attempts > 0:
            remaining_attempts = quiz.max_attempts - attempts_count
            if remaining_attempts <= 0:
                is_blocked = True
                remaining_attempts = 0
        
        quizzes_with_attempts.append({
            'quiz': quiz,
            'attempts_count': attempts_count,
            'is_blocked': is_blocked,
            'remaining_attempts': remaining_attempts,
            'status_message': status_message
        })

    context = {'quizzes_with_attempts': quizzes_with_attempts}
    return render(request, 'quizzes/quiz_list.html', context)

@login_required
def quiz_detail_view(request, quiz_id):
    # Оптимизация: предзагружаем связанные объекты
    quiz = get_object_or_404(
        Quiz.objects.prefetch_related(
            'questions__choices',
            'questions__test_cases'
        ),
        id=quiz_id
    )
    now = timezone.now()
    
    if quiz.start_date and now < quiz.start_date: return redirect('quiz_list') 
    if quiz.end_date and now > quiz.end_date: return redirect('quiz_list') 
    
    if quiz.max_attempts > 0:
        attempts_count = UserResult.objects.filter(user=request.user, quiz=quiz).count()
        if attempts_count >= quiz.max_attempts: return redirect('quiz_list')

    # Находим уже решенные вопросы
    correctly_answered_question_ids = UserAnswer.objects.filter(
        user_result__user=request.user,
        user_result__quiz=quiz,
        is_correct=True
    ).values_list('question_id', flat=True).distinct()
    
    # Считаем, сколько баллов уже "в кармане"
    already_earned_score = len(correctly_answered_question_ids)

    # Исключаем решенные из списка для показа
    # Вопросы уже предзагружены через prefetch_related
    questions_to_show = list(quiz.questions.exclude(id__in=correctly_answered_question_ids))
    
    # Восстанавливаем код из последней неудачной попытки для задач с кодом
    last_failed_attempt = UserResult.objects.filter(
        user=request.user,
        quiz=quiz
    ).order_by('-date_completed').first()
    
    last_attempt_codes = {}
    if last_failed_attempt:
        # Получаем код из последней попытки для вопросов, которые были решены неверно
        failed_code_answers = UserAnswer.objects.filter(
            user_result=last_failed_attempt,
            question__question_type='code',
            is_correct=False,
            code_answer__isnull=False
        ).exclude(code_answer='').select_related('question')
        
        # Создаем словарь: question_id -> code_answer для быстрого доступа в шаблоне
        last_attempt_codes = {answer.question_id: answer.code_answer for answer in failed_code_answers}

    if request.method == 'POST':
        current_attempt_score = 0
        
        duration = None
        start_time_str = request.session.get(f'quiz_{quiz_id}_start')
        if start_time_str:
            start_time = datetime.datetime.fromisoformat(start_time_str)
            end_time = timezone.now()
            duration = end_time - start_time
            if f'quiz_{quiz_id}_start' in request.session: del request.session[f'quiz_{quiz_id}_start']

        user_result = UserResult.objects.create(user=request.user, quiz=quiz, score=0, duration=duration)

        # Оптимизация: предзагружаем все choices в словарь для быстрого доступа
        all_choices = {}
        for question in questions_to_show:
            if question.question_type == 'choice':
                all_choices[question.id] = {choice.id: choice for choice in question.choices.all()}

        # Создаем список UserAnswer для bulk_create
        user_answers_to_create = []

        for question in questions_to_show:
            user_input = request.POST.get(f'question_{question.id}')
            is_correct = False
            selected_choice = None
            text_answer = None
            code_answer = None
            error_log = None 

            if question.question_type == 'choice':
                if user_input:
                    # Используем предзагруженные choices
                    choice_dict = all_choices.get(question.id, {})
                    selected_choice = choice_dict.get(int(user_input)) if user_input.isdigit() else None
                    if selected_choice and selected_choice.is_correct:
                        is_correct = True
                        current_attempt_score += 1
            
            elif question.question_type == 'text':
                text_answer = user_input
                if user_input and question.correct_text_answer:
                    if user_input.strip().lower() == question.correct_text_answer.strip().lower():
                        is_correct = True
                        current_attempt_score += 1

            elif question.question_type == 'code':
                code_answer = user_input
                if user_input:
                    all_tests_passed = True
                    # test_cases уже предзагружены через prefetch_related
                    test_cases = list(question.test_cases.all())
                    
                    if not test_cases:
                        all_tests_passed = False 
                        error_log = "Нет тестовых примеров для проверки."
                    
                    extra_files = {}
                    if question.data_file:
                        try:
                            with question.data_file.open('rb') as f:
                                content = f.read()
                                filename = os.path.basename(question.data_file.name)
                                extra_files[filename] = content
                        except Exception as e:
                            error_log = f"Ошибка чтения файла задания: {e}"
                            all_tests_passed = False

                    if all_tests_passed: 
                        for test_case in test_cases:
                            output, error = run_code_in_docker(user_input, test_case.input_data, extra_files)
                            
                            if error:
                                all_tests_passed = False
                                error_log = error 
                                break
                            
                            if normalize_output(output) != normalize_output(test_case.output_data):
                                all_tests_passed = False
                                # Скрываем правильный ответ от пользователя
                                error_log = f"Неверный ответ на тесте.\nВходные данные: {test_case.input_data}\nВаш ответ: {output}"
                                break
                    
                    if all_tests_passed:
                        is_correct = True
                        current_attempt_score += 1

            user_answers_to_create.append(
                UserAnswer(
                    user_result=user_result,
                    question=question,
                    selected_choice=selected_choice,
                    text_answer=text_answer,
                    code_answer=code_answer,
                    error_log=error_log, 
                    is_correct=is_correct
                )
            )
        
        # Оптимизация: создаем все ответы одним запросом
        UserAnswer.objects.bulk_create(user_answers_to_create)
        
        # Финальный балл = (баллы за эту попытку) + (баллы за старые решенные вопросы)
        total_score = current_attempt_score + already_earned_score
        
        user_result.score = total_score
        user_result.save()
        
        # Получаем неудачные ответы для детального отчета
        failed_answers = UserAnswer.objects.filter(
            user_result=user_result,
            is_correct=False
        ).select_related('question').order_by('question_id')
        
        # Используем предзагруженные вопросы вместо запроса к БД
        total_questions = quiz.questions.count() if hasattr(quiz.questions, 'count') else len(list(quiz.questions.all()))
        
        return render(request, 'quizzes/quiz_result.html', {
            'quiz': quiz,
            'score': total_score,
            'total': total_questions,  # Общее кол-во вопросов в тесте
            'failed_answers': failed_answers,  # Неудачные ответы для детального отчета
            'user_result': user_result,
        })

    request.session[f'quiz_{quiz_id}_start'] = timezone.now().isoformat()
    # Конвертируем ключи в строки для JSON сериализации
    last_attempt_codes_json = json.dumps({str(k): v for k, v in last_attempt_codes.items()})
    
    return render(request, 'quizzes/quiz_detail.html', {
        'quiz': quiz, 
        'questions_to_show': questions_to_show,
        'last_attempt_codes': last_attempt_codes,  # Код из последней неудачной попытки (для шаблона)
        'last_attempt_codes_json': last_attempt_codes_json,  # JSON версия для JavaScript
    })

# --- СТАТИСТИКА (без изменений) ---
@user_passes_test(lambda u: u.is_superuser)
def quiz_stats_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    groups = StudentGroup.objects.filter(students__user__userresult__quiz=quiz).distinct()
    users_without_group = User.objects.filter(userresult__quiz=quiz, profile__group__isnull=True).distinct()

    stats_by_group = []

    for group in groups:
        group_data = {
            'group_name': group.name,
            'students': []
        }
        students = User.objects.filter(profile__group=group, userresult__quiz=quiz).distinct()
        for user in students:
            user_stats = get_user_stats(user, quiz)
            group_data['students'].append(user_stats)
        stats_by_group.append(group_data)

    if users_without_group.exists():
        no_group_data = {
            'group_name': 'Без класса',
            'students': []
        }
        for user in users_without_group:
            user_stats = get_user_stats(user, quiz)
            no_group_data['students'].append(user_stats)
        stats_by_group.append(no_group_data)
    
    return render(request, 'quizzes/quiz_stats.html', {'quiz': quiz, 'stats_by_group': stats_by_group})

def get_user_stats(user, quiz):
    results = UserResult.objects.filter(user=user, quiz=quiz).order_by('-date_completed')
    last_result = results.first()
    best_score = results.aggregate(Max('score'))['score__max']
    
    full_name = f"{user.last_name} {user.first_name}".strip()
    if not full_name:
        full_name = user.username

    return {
        'user': user,
        'full_name': full_name,
        'attempts_count': results.count(),
        'last_score': last_result.score,
        'best_score': best_score,
        'last_duration': last_result.duration,
        'last_date': last_result.date_completed,
    }

@user_passes_test(lambda u: u.is_superuser)
def user_attempts_view(request, quiz_id, user_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user = get_object_or_404(User, id=user_id)
    results = UserResult.objects.filter(quiz=quiz, user=user).order_by('-date_completed')
    
    full_name = f"{user.last_name} {user.first_name}".strip() or user.username
    
    return render(request, 'quizzes/user_attempts.html', {
        'quiz': quiz, 
        'student': user, 
        'student_name': full_name,
        'results': results
    })

@user_passes_test(lambda u: u.is_superuser)
def attempt_detail_view(request, result_id):
    result = get_object_or_404(UserResult, id=result_id)
    answers = result.answers.all()
    
    full_name = f"{result.user.last_name} {result.user.first_name}".strip() or result.user.username

    return render(request, 'quizzes/attempt_detail.html', {
        'result': result, 
        'answers': answers,
        'student_name': full_name
    })
