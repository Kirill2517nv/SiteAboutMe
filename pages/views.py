import json
import os
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from .models import ContentBlock


def home_page_view(request):
    blocks = ContentBlock.objects.filter(page='home').order_by('order')
    
    # Для staff передаём блоки в JSON формате
    blocks_json = []
    if request.user.is_staff:
        for b in blocks:
            blocks_json.append({
                'id': b.id,
                'type': b.block_type,
                'title': b.title or '',
                'content': b.content or '',
                'image': b.image.url if b.image else '',
                'linkUrl': b.link_url or '',
                'order': b.order,
                'layout': b.layout or 'vertical',
                'imageWidth': b.image_width or 100,
                'imageHeight': b.image_height or 0,
                'imageAlign': b.image_align or 'center',
                'textAlign': b.text_align or 'left',
                'imageCropX': b.image_crop_x or 0,
                'imageCropY': b.image_crop_y or 0,
                'imageCropWidth': b.image_crop_width or 0,
                'imageCropHeight': b.image_crop_height or 0,
                'imageNaturalWidth': b.image_natural_width or 0,
                'imageNaturalHeight': b.image_natural_height or 0,
                'textPosX': b.text_pos_x,
                'textPosY': b.text_pos_y,
                'imagePosX': b.image_pos_x,
                'imagePosY': b.image_pos_y,
                # Новые поля шрифтов
                'titleFontSize': getattr(b, 'title_font_size', 'text-xl'),
                'titleFontFamily': getattr(b, 'title_font_family', 'font-sans'),
                'titleColor': getattr(b, 'title_color', 'text-gray-900'),
                'contentFontSize': getattr(b, 'content_font_size', 'text-base'),
                'contentFontFamily': getattr(b, 'content_font_family', 'font-sans'),
                'contentColor': getattr(b, 'content_color', 'text-gray-700'),
                'cardBg': getattr(b, 'card_bg', 'bg-white'),
            })
    
    context = {
        'blocks': blocks,
        'blocks_json': json.dumps(blocks_json, ensure_ascii=False),
        'page_type': 'home',
    }
    return render(request, 'home.html', context)


def about_page_view(request):
    blocks = ContentBlock.objects.filter(page='about').order_by('order')
    
    # Для staff передаём блоки в JSON формате
    blocks_json = []
    if request.user.is_staff:
        for b in blocks:
            blocks_json.append({
                'id': b.id,
                'type': b.block_type,
                'title': b.title or '',
                'content': b.content or '',
                'image': b.image.url if b.image else '',
                'linkUrl': b.link_url or '',
                'order': b.order,
                'layout': b.layout or 'vertical',
                'imageWidth': b.image_width or 100,
                'imageHeight': b.image_height or 0,
                'imageAlign': b.image_align or 'center',
                'textAlign': b.text_align or 'left',
                'imageCropX': b.image_crop_x or 0,
                'imageCropY': b.image_crop_y or 0,
                'imageCropWidth': b.image_crop_width or 0,
                'imageCropHeight': b.image_crop_height or 0,
                'imageNaturalWidth': b.image_natural_width or 0,
                'imageNaturalHeight': b.image_natural_height or 0,
                'textPosX': b.text_pos_x,
                'textPosY': b.text_pos_y,
                'imagePosX': b.image_pos_x,
                'imagePosY': b.image_pos_y,
                # Новые поля шрифтов
                'titleFontSize': getattr(b, 'title_font_size', 'text-xl'),
                'titleFontFamily': getattr(b, 'title_font_family', 'font-sans'),
                'titleColor': getattr(b, 'title_color', 'text-gray-900'),
                'contentFontSize': getattr(b, 'content_font_size', 'text-base'),
                'contentFontFamily': getattr(b, 'content_font_family', 'font-sans'),
                'contentColor': getattr(b, 'content_color', 'text-gray-700'),
                'cardBg': getattr(b, 'card_bg', 'bg-white'),
            })
    
    context = {
        'blocks': blocks,
        'blocks_json': json.dumps(blocks_json, ensure_ascii=False),
        'page_type': 'about',
    }
    return render(request, 'about.html', context)


@staff_member_required
@require_POST
def content_save_api(request):
    """API для сохранения блоков контента (главная и 'Обо мне')."""
    try:
        data = json.loads(request.body)
        page = data.get('page')
        blocks_data = data.get('blocks', [])
        
        if page not in ['home', 'about']:
            return JsonResponse({'error': 'Неверный тип страницы'}, status=400)
        
        # Получаем существующие блоки
        existing_blocks = {str(b.id): b for b in ContentBlock.objects.filter(page=page)}
        
        # Множество ID блоков из запроса (для определения удалённых)
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
                block = ContentBlock(page=page)
            
            block.block_type = block_data.get('type', 'text')
            block.title = block_data.get('title', '')
            block.content = block_data.get('content', '')
            block.link_url = block_data.get('link_url', '')
            block.order = block_data.get('order', 0)
            
            # Настройки layout
            block.layout = block_data.get('layout', 'vertical')
            block.image_width = block_data.get('image_width', 100)
            block.image_height = block_data.get('image_height', 0)
            block.image_align = block_data.get('image_align', 'center')
            block.image_object_fit = block_data.get('image_object_fit', 'cover')
            block.image_border_radius = block_data.get('image_border_radius', '0.5rem')
            block.image_opacity = block_data.get('image_opacity', 100)
            block.image_position_x = block_data.get('image_position_x', 50)
            block.image_position_y = block_data.get('image_position_y', 50)
            block.text_align = block_data.get('text_align', 'left')
            
            # Настройки шрифтов
            block.title_font_size = block_data.get('title_font_size', 'text-xl')
            block.title_font_family = block_data.get('title_font_family', 'font-sans')
            block.title_color = block_data.get('title_color', 'text-gray-900')
            block.content_font_size = block_data.get('content_font_size', 'text-base')
            block.content_font_family = block_data.get('content_font_family', 'font-sans')
            block.content_color = block_data.get('content_color', 'text-gray-700')
            block.card_bg = block_data.get('card_bg', 'bg-white')
            
            # Обработка изображения - сохраняем путь если передан
            image_url = block_data.get('image', '')
            if image_url:
                # Если это путь к существующему файлу в media, извлекаем относительный путь
                if image_url.startswith(settings.MEDIA_URL):
                    relative_path = image_url[len(settings.MEDIA_URL):]
                    block.image = relative_path
                elif image_url.startswith('/'):
                    # Абсолютный путь - пробуем извлечь
                    block.image = image_url.lstrip('/')
            
            block.save()
            saved_blocks.append({
                'id': block.id,
                'order': block.order
            })
        
        # Удаляем блоки, которые не пришли в запросе
        for block_id, block in existing_blocks.items():
            if block_id not in received_ids:
                # Удаляем файл изображения если есть
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
def content_upload_image_api(request):
    """API для загрузки изображения."""
    try:
        image = request.FILES.get('image')
        block_id = request.POST.get('block_id')
        page = request.POST.get('page')
        
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
        if block_id and not block_id.startswith('new_'):
            try:
                block = ContentBlock.objects.get(id=block_id)
                # Удаляем старое изображение
                if block.image:
                    try:
                        os.remove(block.image.path)
                    except OSError:
                        pass
                block.image = image
                block.save()
                return JsonResponse({'success': True, 'url': block.image.url})
            except ContentBlock.DoesNotExist:
                pass
        
        # Для нового блока - просто сохраняем файл и возвращаем URL
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        import uuid
        
        ext = os.path.splitext(image.name)[1]
        filename = f"content/{uuid.uuid4()}{ext}"
        path = default_storage.save(filename, ContentFile(image.read()))
        url = settings.MEDIA_URL + path
        
        return JsonResponse({'success': True, 'url': url, 'path': path})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
