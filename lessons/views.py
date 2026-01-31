import json
import os
import mimetypes
import re
from urllib.parse import quote

from django.shortcuts import render, get_object_or_404
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings

from .models import Lesson, Section, LessonBlock


def _attachment_content_disposition(filename: str) -> str:
    safe = (filename or "download").replace("\r", "").replace("\n", "")
    ascii_fallback = re.sub(r"[^A-Za-z0-9.\-_]", "_", safe) or "download"
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(safe)}'


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
    blocks = lesson.blocks.all().order_by('order')
    context = {
        'lesson': lesson,
        'blocks': blocks,
        'page_type': 'lesson',
    }
    return render(request, 'lessons/lesson_detail.html', context)


def lesson_file_download_view(request, lesson_id):
    """Download Lesson.file with a stable filename across browsers/OS."""
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if not lesson.file:
        raise Http404("Файл не найден")

    filename = os.path.basename(lesson.file.name)
    content_type, _ = mimetypes.guess_type(filename)

    response = FileResponse(
        lesson.file.open("rb"),
        as_attachment=True,
        content_type=content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = _attachment_content_disposition(filename)
    return response


@staff_member_required
@require_POST
def lesson_save_api(request, lesson_id):
    """API для сохранения блоков урока."""
    try:
        lesson = get_object_or_404(Lesson, id=lesson_id)
        data = json.loads(request.body)
        blocks_data = data.get('blocks', [])
        
        # Получаем существующие блоки
        existing_blocks = {str(b.id): b for b in LessonBlock.objects.filter(lesson=lesson)}
        
        # Множество ID блоков из запроса
        received_ids = set()
        saved_blocks = []
        
        for block_data in blocks_data:
            block_id = block_data.get('id')
            
            if block_id and str(block_id) in existing_blocks:
                # Обновляем существующий блок
                block = existing_blocks[str(block_id)]
                received_ids.add(str(block_id))
            else:
                # Создаём новый блок
                block = LessonBlock(lesson=lesson)
            
            block.block_type = block_data.get('type', 'text')
            block.title = block_data.get('title', '')
            block.content = block_data.get('content', '')
            block.order = block_data.get('order', 0)
            
            # Настройки layout
            block.layout = block_data.get('layout', 'vertical')
            block.image_width = block_data.get('image_width', 100)
            block.image_height = block_data.get('image_height', 0)
            block.image_align = block_data.get('image_align', 'center')
            block.image_crop_x = block_data.get('image_crop_x', 0)
            block.image_crop_y = block_data.get('image_crop_y', 0)
            block.image_crop_width = block_data.get('image_crop_width', 0)
            block.image_crop_height = block_data.get('image_crop_height', 0)
            block.image_natural_width = block_data.get('image_natural_width', 0)
            block.image_natural_height = block_data.get('image_natural_height', 0)
            block.text_pos_x = block_data.get('text_pos_x')
            block.text_pos_y = block_data.get('text_pos_y')
            block.image_pos_x = block_data.get('image_pos_x')
            block.image_pos_y = block_data.get('image_pos_y')
            block.text_align = block_data.get('text_align', 'left')
            
            # Обработка изображения
            image_url = block_data.get('image', '')
            if image_url:
                if image_url.startswith(settings.MEDIA_URL):
                    relative_path = image_url[len(settings.MEDIA_URL):]
                    block.image = relative_path
                elif image_url.startswith('/'):
                    block.image = image_url.lstrip('/')
            
            block.save()
            saved_blocks.append({
                'id': block.id,
                'order': block.order
            })
        
        # Удаляем блоки, которые не пришли в запросе
        for block_id, block in existing_blocks.items():
            if block_id not in received_ids:
                if block.image:
                    try:
                        os.remove(block.image.path)
                    except OSError:
                        pass
                block.delete()
        
        return JsonResponse({'success': True, 'blocks': saved_blocks})
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
@require_POST
def lesson_upload_image_api(request, lesson_id):
    """API для загрузки изображения в блок урока."""
    try:
        lesson = get_object_or_404(Lesson, id=lesson_id)
        image = request.FILES.get('image')
        block_id = request.POST.get('block_id')
        
        if not image:
            return JsonResponse({'error': 'Изображение не передано'}, status=400)
        
        # Проверяем тип файла
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if image.content_type not in allowed_types:
            return JsonResponse({'error': 'Неподдерживаемый тип файла'}, status=400)
        
        # Проверяем размер (макс 5MB)
        if image.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'Файл слишком большой (макс. 5MB)'}, status=400)
        
        # Если передан block_id, обновляем существующий блок
        if block_id and not str(block_id).startswith('new_'):
            try:
                block = LessonBlock.objects.get(id=block_id, lesson=lesson)
                # Удаляем старое изображение
                if block.image:
                    try:
                        os.remove(block.image.path)
                    except OSError:
                        pass
                block.image = image
                block.save()
                return JsonResponse({'success': True, 'url': block.image.url})
            except LessonBlock.DoesNotExist:
                pass
        
        # Для нового блока - сохраняем файл и возвращаем URL
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        import uuid
        
        ext = os.path.splitext(image.name)[1]
        filename = f"lessons_content/{uuid.uuid4()}{ext}"
        path = default_storage.save(filename, ContentFile(image.read()))
        url = settings.MEDIA_URL + path
        
        return JsonResponse({'success': True, 'url': url, 'path': path})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
