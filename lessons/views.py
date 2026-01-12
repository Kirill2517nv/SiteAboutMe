from django.shortcuts import render, get_object_or_404
from .models import Lesson

def lesson_list_view(request):
    lessons = Lesson.objects.all()
    context = {'lessons': lessons}
    return render(request, 'lessons/lesson_list.html', context)

def lesson_detail_view(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    context = {'lesson': lesson}
    return render(request, 'lessons/lesson_detail.html', context)
