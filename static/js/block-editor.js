/**
 * Block Editor - Alpine.js компонент для редактирования контента
 */

function blockEditor(config) {
    return {
        // Конфигурация
        apiSaveUrl: config.apiSaveUrl || '',
        apiUploadUrl: config.apiUploadUrl || '',
        csrfToken: config.csrfToken || '',
        pageType: config.pageType || 'home',
        
        // Состояние
        isEditMode: false,
        blocks: [],
        originalBlocks: [],
        selectedBlock: null,
        selectedBlockIndex: -1,
        activeTab: 'basic',
        isSaving: false,
        
        // Опции для select полей
        blockTypes: [
            { value: 'text', label: 'Текст' },
            { value: 'image', label: 'Изображение' },
            { value: 'text_image', label: 'Текст + Изображение' }
        ],
        fontSizes: [
            { value: 'text-sm', label: 'Маленький' },
            { value: 'text-base', label: 'Обычный' },
            { value: 'text-lg', label: 'Увеличенный' },
            { value: 'text-xl', label: 'Большой' },
            { value: 'text-2xl', label: 'Очень большой' },
            { value: 'text-3xl', label: 'Огромный' }
        ],
        colors: [
            { value: 'text-gray-900', label: 'Чёрный' },
            { value: 'text-gray-700', label: 'Тёмно-серый' },
            { value: 'text-gray-500', label: 'Серый' },
            { value: 'text-white', label: 'Белый' },
            { value: 'text-blue-600', label: 'Синий' },
            { value: 'text-green-600', label: 'Зелёный' },
            { value: 'text-red-600', label: 'Красный' },
            { value: 'text-yellow-600', label: 'Жёлтый' },
            { value: 'text-purple-600', label: 'Фиолетовый' },
            { value: 'text-pink-600', label: 'Розовый' }
        ],
        bgColors: [
            { value: 'bg-white', label: 'Белый' },
            { value: 'bg-gray-50', label: 'Светло-серый' },
            { value: 'bg-gray-100', label: 'Серый' },
            { value: 'bg-blue-50', label: 'Светло-синий' },
            { value: 'bg-green-50', label: 'Светло-зелёный' },
            { value: 'bg-yellow-50', label: 'Светло-жёлтый' },
            { value: 'bg-red-50', label: 'Светло-красный' },
            { value: 'bg-purple-50', label: 'Светло-фиолетовый' }
        ],
        layouts: [
            { value: 'vertical', label: 'Вертикально' },
            { value: 'horizontal', label: 'Горизонтально (текст слева)' },
            { value: 'horizontal-reverse', label: 'Горизонтально (картинка слева)' }
        ],
        objectFits: [
            { value: 'cover', label: 'Заполнить (cover)' },
            { value: 'contain', label: 'Вместить (contain)' },
            { value: 'fill', label: 'Растянуть (fill)' },
            { value: 'none', label: 'Оригинал (none)' }
        ],
        borderRadiuses: [
            { value: '0', label: 'Без скругления' },
            { value: '0.375rem', label: 'Маленькое' },
            { value: '0.5rem', label: 'Среднее' },
            { value: '0.75rem', label: 'Большое' },
            { value: '1rem', label: 'Очень большое' },
            { value: '9999px', label: 'Круглое' }
        ],
        
        // Инициализация
        init() {
            this.loadBlocksFromDOM();
        },
        
        // Загрузка блоков из DOM
        loadBlocksFromDOM() {
            const blockElements = this.$el.querySelectorAll('[data-block-id]');
            this.blocks = [];
            
            blockElements.forEach((el, index) => {
                this.blocks.push({
                    id: el.dataset.blockId,
                    block_type: el.dataset.blockType || 'text',
                    title: el.dataset.blockTitle || '',
                    content: el.dataset.blockContent || '',
                    image: el.dataset.blockImage || '',
                    link_url: el.dataset.blockLinkUrl || '',
                    order: parseInt(el.dataset.blockOrder) || index,
                    layout: el.dataset.blockLayout || 'vertical',
                    image_width: parseInt(el.dataset.blockImageWidth) || 100,
                    image_height: parseInt(el.dataset.blockImageHeight) || 0,
                    image_align: el.dataset.blockImageAlign || 'center',
                    image_object_fit: el.dataset.blockImageObjectFit || 'cover',
                    image_border_radius: el.dataset.blockImageBorderRadius || '0.5rem',
                    image_opacity: parseInt(el.dataset.blockImageOpacity) || 100,
                    image_position_x: parseInt(el.dataset.blockImagePositionX) || 50,
                    image_position_y: parseInt(el.dataset.blockImagePositionY) || 50,
                    text_align: el.dataset.blockTextAlign || 'left',
                    title_font_size: el.dataset.blockTitleFontSize || 'text-xl',
                    title_color: el.dataset.blockTitleColor || 'text-gray-900',
                    content_font_size: el.dataset.blockContentFontSize || 'text-base',
                    content_color: el.dataset.blockContentColor || 'text-gray-700',
                    card_bg: el.dataset.blockCardBg || 'bg-white',
                    _isNew: false
                });
            });
            
            this.blocks.sort((a, b) => a.order - b.order);
        },
        
        // Переключение режима редактирования
        toggleEditMode() {
            if (this.isEditMode) {
                this.exitEditMode();
            } else {
                this.enterEditMode();
            }
        },
        
        enterEditMode() {
            this.originalBlocks = JSON.parse(JSON.stringify(this.blocks));
            this.isEditMode = true;
            this.selectedBlock = null;
            this.selectedBlockIndex = -1;
        },
        
        exitEditMode(save = false) {
            if (!save) {
                this.blocks = JSON.parse(JSON.stringify(this.originalBlocks));
            }
            this.isEditMode = false;
            this.selectedBlock = null;
            this.selectedBlockIndex = -1;
            this.activeTab = 'basic';
        },
        
        // Выбор блока для редактирования
        selectBlock(index) {
            if (!this.isEditMode) return;
            
            this.selectedBlockIndex = index;
            this.selectedBlock = this.blocks[index];
            this.activeTab = 'basic';
        },
        
        // Закрытие sidebar
        closeSidebar() {
            this.selectedBlock = null;
            this.selectedBlockIndex = -1;
        },
        
        // Добавление нового блока
        addBlock(type = 'text') {
            const newBlock = {
                id: 'new_' + Date.now(),
                block_type: type,
                title: '',
                content: '',
                image: '',
                link_url: '',
                order: this.blocks.length,
                layout: 'vertical',
                image_width: 100,
                image_height: 0,
                image_align: 'center',
                image_object_fit: 'cover',
                image_border_radius: '0.5rem',
                image_opacity: 100,
                image_position_x: 50,
                image_position_y: 50,
                text_align: 'left',
                title_font_size: 'text-xl',
                title_color: 'text-gray-900',
                content_font_size: 'text-base',
                content_color: 'text-gray-700',
                card_bg: 'bg-white',
                _isNew: true
            };
            
            this.blocks.push(newBlock);
            this.selectBlock(this.blocks.length - 1);
        },
        
        // Удаление блока
        deleteBlock() {
            if (this.selectedBlockIndex === -1) return;
            
            if (confirm('Удалить этот блок?')) {
                this.blocks.splice(this.selectedBlockIndex, 1);
                this.updateBlockOrders();
                this.closeSidebar();
            }
        },
        
        // Перемещение блока вверх
        moveBlockUp() {
            if (this.selectedBlockIndex <= 0) return;
            
            const idx = this.selectedBlockIndex;
            [this.blocks[idx - 1], this.blocks[idx]] = [this.blocks[idx], this.blocks[idx - 1]];
            this.selectedBlockIndex = idx - 1;
            this.updateBlockOrders();
        },
        
        // Перемещение блока вниз
        moveBlockDown() {
            if (this.selectedBlockIndex >= this.blocks.length - 1) return;
            
            const idx = this.selectedBlockIndex;
            [this.blocks[idx], this.blocks[idx + 1]] = [this.blocks[idx + 1], this.blocks[idx]];
            this.selectedBlockIndex = idx + 1;
            this.updateBlockOrders();
        },
        
        // Обновление порядка блоков
        updateBlockOrders() {
            this.blocks.forEach((block, index) => {
                block.order = index;
            });
        },
        
        // Загрузка изображения
        async uploadImage(event) {
            const file = event.target.files[0];
            if (!file) return;
            
            const formData = new FormData();
            formData.append('image', file);
            formData.append('block_id', this.selectedBlock.id);
            
            try {
                const response = await fetch(this.apiUploadUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': this.csrfToken
                    },
                    body: formData
                });
                
                if (response.ok) {
                    const data = await response.json();
                    this.selectedBlock.image = data.url;
                } else {
                    const errorData = await response.json();
                    alert('Ошибка загрузки: ' + (errorData.error || 'Неизвестная ошибка'));
                }
            } catch (error) {
                console.error('Upload error:', error);
                alert('Ошибка при загрузке изображения');
            }
            
            // Сброс input
            event.target.value = '';
        },
        
        // Удаление изображения
        removeImage() {
            if (this.selectedBlock) {
                this.selectedBlock.image = '';
            }
        },
        
        // Сохранение всех изменений
        async save() {
            this.isSaving = true;
            
            const blocksData = this.blocks.map(block => ({
                id: block.id.toString().startsWith('new_') ? null : block.id,
                type: block.block_type,
                title: block.title || '',
                content: block.content || '',
                image: block.image || '',
                link_url: block.link_url || '',
                order: block.order,
                layout: block.layout || 'vertical',
                image_width: block.image_width || 100,
                image_height: block.image_height || 0,
                image_align: block.image_align || 'center',
                image_object_fit: block.image_object_fit || 'cover',
                image_border_radius: block.image_border_radius || '0.5rem',
                image_opacity: block.image_opacity || 100,
                image_position_x: block.image_position_x || 50,
                image_position_y: block.image_position_y || 50,
                text_align: block.text_align || 'left',
                title_font_size: block.title_font_size || 'text-xl',
                title_color: block.title_color || 'text-gray-900',
                content_font_size: block.content_font_size || 'text-base',
                content_color: block.content_color || 'text-gray-700',
                card_bg: block.card_bg || 'bg-white'
            }));
            
            try {
                const response = await fetch(this.apiSaveUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken
                    },
                    body: JSON.stringify({
                        page: this.pageType,
                        blocks: blocksData
                    })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    // Обновляем ID новых блоков
                    if (data.blocks) {
                        data.blocks.forEach(savedBlock => {
                            const block = this.blocks.find(b => b.order === savedBlock.order);
                            if (block && block.id.toString().startsWith('new_')) {
                                block.id = savedBlock.id;
                                block._isNew = false;
                            }
                        });
                    }
                    
                    alert('Изменения сохранены!');
                    this.exitEditMode(true);
                    // Перезагружаем страницу для отображения изменений
                    window.location.reload();
                } else {
                    const errorData = await response.json();
                    alert('Ошибка сохранения: ' + (errorData.error || 'Неизвестная ошибка'));
                }
            } catch (error) {
                console.error('Save error:', error);
                alert('Ошибка при сохранении');
            }
            
            this.isSaving = false;
        },
        
        // Отмена изменений
        cancel() {
            if (confirm('Отменить все изменения?')) {
                this.exitEditMode(false);
            }
        },
        
        // Получить CSS классы для блока
        getBlockClasses(block, index) {
            let classes = 'relative transition-all duration-200 ';
            
            if (this.isEditMode) {
                classes += 'cursor-pointer hover:ring-2 hover:ring-blue-400 ';
                
                if (this.selectedBlockIndex === index) {
                    classes += 'ring-2 ring-blue-500 ';
                }
            }
            
            return classes;
        },
        
        // Получить inline стили для изображения
        getImageStyles(block) {
            let styles = 'display: block; ';
            
            // Ширина
            styles += `width: ${block.image_width || 100}%;`;
            
            // Высота
            if (block.image_height && parseInt(block.image_height) > 0) {
                styles += `height: ${block.image_height}px;`;
            } else {
                styles += 'aspect-ratio: 16/9;';
            }
            
            // Object-fit
            styles += `object-fit: ${block.image_object_fit || 'cover'};`;
            
            // Object-position (для обрезки/фокуса)
            const posX = block.image_position_x !== undefined ? block.image_position_x : 50;
            const posY = block.image_position_y !== undefined ? block.image_position_y : 50;
            styles += `object-position: ${posX}% ${posY}%;`;
            
            // Скругление
            if (block.image_border_radius && block.image_border_radius !== '0') {
                styles += `border-radius: ${block.image_border_radius};`;
            }
            
            // Прозрачность
            if (block.image_opacity && parseInt(block.image_opacity) < 100) {
                styles += `opacity: ${block.image_opacity / 100};`;
            }
            
            // Выравнивание через margin
            if (block.image_align === 'center') {
                styles += 'margin-left: auto; margin-right: auto;';
            } else if (block.image_align === 'right') {
                styles += 'margin-left: auto;';
            }
            
            return styles;
        },
        
        // Получить стили для контейнера изображения
        getImageContainerStyles(block) {
            let styles = '';
            
            if (block.image_align === 'center') {
                styles += 'margin: 0 auto;';
            } else if (block.image_align === 'right') {
                styles += 'margin-left: auto;';
            }
            
            if (block.image_width) {
                styles += `width: ${block.image_width}%;`;
            }
            
            return styles;
        },
        
        // Получить название типа блока
        getBlockTypeName(type) {
            const found = this.blockTypes.find(t => t.value === type);
            return found ? found.label : type;
        }
    };
}

// Экспорт для использования
window.blockEditor = blockEditor;
