from django.shortcuts import render, get_object_or_404
from django.http import FileResponse, Http404, HttpResponse
from django.conf import settings
from django.utils.http import content_disposition_header
from .models import Lesson, Section
import os
import mimetypes

def lesson_list_view(request):
    sections = Section.objects.prefetch_related('lessons').all()
    orphan_lessons = Lesson.objects.filter(section__isnull=True)
    context = {
        'sections': sections,
        'orphan_lessons': orphan_lessons
    }
    return render(request, 'lessons/lesson_list.html', context)

def lesson_detail_view(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    context = {'lesson': lesson}
    return render(request, 'lessons/lesson_detail.html', context)

def lesson_file_download_view(request, lesson_id):
    """
    Download Lesson.file with a stable filename across browsers/OS.
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if not lesson.file:
        raise Http404("Файл не найден")

    filename = os.path.basename(lesson.file.name)
    content_type, _ = mimetypes.guess_type(filename)

    if getattr(settings, "USE_X_ACCEL_REDIRECT", False):
        internal_path = f"/_protected_media/{lesson.file.name.lstrip('/')}"
        response = HttpResponse()
        response["X-Accel-Redirect"] = internal_path
        response["Content-Type"] = content_type or "application/octet-stream"
        response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=filename)
        response["Cache-Control"] = "no-store"
        return response

    response = FileResponse(
        lesson.file.open("rb"),
        as_attachment=True,
        content_type=content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=filename)
    return response
