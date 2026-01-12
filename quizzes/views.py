from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Max
from .models import Quiz, Choice, UserResult, UserAnswer, TestCase
from accounts.models import StudentGroup
import datetime
from .utils import run_code_in_docker

def quiz_list_view(request):
    quizzes = Quiz.objects.all()
    
    quizzes_with_attempts = []
    now = timezone.now()
    
    for quiz in quizzes:
        attempts_count = 0
        is_blocked = False
        remaining_attempts = None
        status_message = None # Сообщение о статусе (не начался, закончился)
        
        # Проверка по датам
        is_open_by_date = True
        
        if quiz.start_date and now < quiz.start_date:
            is_open_by_date = False
            is_blocked = True
            status_message = f"Откроется: {quiz.start_date.strftime('%d.%m.%Y %H:%M')}"
        
        elif quiz.end_date and now > quiz.end_date:
            is_open_by_date = False
            is_blocked = True
            status_message = f"Завершился: {quiz.end_date.strftime('%d.%m.%Y %H:%M')}"

        if request.user.is_authenticated:
            attempts_count = UserResult.objects.filter(user=request.user, quiz=quiz).count()
            
            if quiz.max_attempts > 0:
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
    quiz = get_object_or_404(Quiz, id=quiz_id)
    now = timezone.now()
    
    # 1. Проверка по датам
    if quiz.start_date and now < quiz.start_date:
        return redirect('quiz_list') # Или страница ошибки "Рано"
    
    if quiz.end_date and now > quiz.end_date:
        return redirect('quiz_list') # Или страница ошибки "Поздно"

    # 2. Проверка лимита попыток
    if quiz.max_attempts > 0:
        attempts_count = UserResult.objects.filter(user=request.user, quiz=quiz).count()
        if attempts_count >= quiz.max_attempts:
            return redirect('quiz_list')

    if request.method == 'POST':
        score = 0
        total_questions = quiz.questions.count()
        
        duration = None
        start_time_str = request.session.get(f'quiz_{quiz_id}_start')
        
        if start_time_str:
            start_time = datetime.datetime.fromisoformat(start_time_str)
            end_time = timezone.now()
            duration = end_time - start_time
            if f'quiz_{quiz_id}_start' in request.session:
                del request.session[f'quiz_{quiz_id}_start']

        user_result = UserResult.objects.create(
            user=request.user,
            quiz=quiz,
            score=0, 
            duration=duration
        )

        for question in quiz.questions.all():
            user_input = request.POST.get(f'question_{question.id}')
            is_correct = False
            selected_choice = None
            text_answer = None
            code_answer = None
            error_log = None 

            if question.question_type == 'choice':
                if user_input:
                    try:
                        selected_choice = Choice.objects.get(id=user_input)
                        if selected_choice.is_correct:
                            is_correct = True
                            score += 1
                    except Choice.DoesNotExist:
                        pass
            
            elif question.question_type == 'text':
                text_answer = user_input
                if user_input and question.correct_text_answer:
                    if user_input.strip().lower() == question.correct_text_answer.strip().lower():
                        is_correct = True
                        score += 1

            elif question.question_type == 'code':
                code_answer = user_input
                if user_input:
                    all_tests_passed = True
                    test_cases = question.test_cases.all()
                    
                    if not test_cases.exists():
                        all_tests_passed = False 
                        error_log = "Нет тестовых примеров для проверки."
                    
                    for test_case in test_cases:
                        output, error = run_code_in_docker(user_input, test_case.input_data)
                        
                        if error:
                            all_tests_passed = False
                            error_log = error 
                            break
                        
                        if output.strip() != test_case.output_data.strip():
                            all_tests_passed = False
                            error_log = f"Неверный ответ на тесте.\nВход: {test_case.input_data}\nОжидалось: {test_case.output_data}\nПолучено: {output}"
                            break
                    
                    if all_tests_passed:
                        is_correct = True
                        score += 1

            UserAnswer.objects.create(
                user_result=user_result,
                question=question,
                selected_choice=selected_choice,
                text_answer=text_answer,
                code_answer=code_answer,
                error_log=error_log, 
                is_correct=is_correct
            )
        
        user_result.score = score
        user_result.save()
        
        return render(request, 'quizzes/quiz_result.html', {
            'quiz': quiz,
            'score': score,
            'total': total_questions
        })

    request.session[f'quiz_{quiz_id}_start'] = timezone.now().isoformat()
    return render(request, 'quizzes/quiz_detail.html', {'quiz': quiz})

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
