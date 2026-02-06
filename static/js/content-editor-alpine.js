/**
 * Универсальный редактор контента на Alpine.js v2
 * С полной поддержкой шрифтов, Cropper.js и улучшенным UI
 */

// Ждём загрузки Alpine и регистрируем компонент
document.addEventListener('DOMContentLoaded', function() {
    // Проверяем, загружен ли Alpine
    if (typeof Alpine === 'undefined') {
        // Если Alpine ещё не загружен, ждём события alpine:init
        document.addEventListener('alpine:init', registerContentEditor);
    } else {
        // Если Alpine уже загружен, регистрируем сразу
        registerContentEditor();
    }
});

// Также слушаем alpine:init на случай если DOMContentLoaded уже прошёл
document.addEventListener('alpine:init', registerContentEditor);

function registerContentEditor() {
    // Проверяем, не зарегистрирован ли уже
    if (window._contentEditorRegistered) return;
    window._contentEditorRegistered = true;
    
    Alpine.data('contentEditor', function(config) {
        return {
            // Конфигурация
            apiSaveUrl: config.apiSaveUrl,
            apiUploadUrl: config.apiUploadUrl,
            csrfToken: config.csrfToken,
            pageType: config.pageType,
            lessonId: config.lessonId || null,
            
            // Состояние
            isEditMode: false,
            isSaving: false,
            blocks: [],
            originalBlocks: [],
            draggedBlockId: null,
            selectedBlockId: null,
            showSettings: false,
            activeCropper: null,
            cropBlockId: null,
            
            // Инициализация
            init: function() {
                // Загружаем блоки из конфига
                var initialBlocks = config.blocks || [];
                this.blocks = initialBlocks.map(function(b) {
                    return Object.assign({}, b, { isNew: false });
                });
                this.blocks.sort(function(a, b) { return a.order - b.order; });
            },
            
            // Получить выбранный блок
            get selectedBlock() {
                var self = this;
                return this.blocks.find(function(b) { return b.id === self.selectedBlockId; }) || null;
            },
            
            // Управление режимом редактирования
            toggleEditMode: function() {
                if (this.isEditMode) {
                    this.exitEditMode(false);
                } else {
                    this.enterEditMode();
                }
            },
            
            enterEditMode: function() {
                this.originalBlocks = JSON.parse(JSON.stringify(this.blocks));
                this.isEditMode = true;
                this.selectedBlockId = null;
                this.showSettings = false;
            },
            
            exitEditMode: function(save) {
                save = save || false;
                // Уничтожаем cropper если активен
                this.destroyCropper();
                
                if (!save) {
                    // Удаляем новые блоки
                    this.blocks = this.blocks.filter(function(b) { return !b.isNew; });
                    // Восстанавливаем оригинальные данные
                    var self = this;
                    this.blocks.forEach(function(block) {
                        var original = self.originalBlocks.find(function(o) { return o.id === block.id; });
                        if (original) {
                            Object.assign(block, original);
                        }
                    });
                    this.blocks.sort(function(a, b) { return a.order - b.order; });
                }
                
                this.isEditMode = false;
                this.selectedBlockId = null;
                this.showSettings = false;
            },
            
            // Выбор блока
            selectBlock: function(block) {
                if (!this.isEditMode) return;
                this.selectedBlockId = block.id;
                this.showSettings = true;
            },
            
            // CRUD блоков
            addBlock: function(type) {
                var newBlock = {
                    id: 'new_' + Date.now(),
                    type: type,
                    title: '',
                    content: '',
                    image: '',
                    linkUrl: '',
                    order: this.blocks.length,
                    layout: 'vertical',
                    imageWidth: 100,
                    imageHeight: 0,
                    imageAlign: 'center',
                    textAlign: 'left',
                    imageCropX: 0,
                    imageCropY: 0,
                    imageCropWidth: 0,
                    imageCropHeight: 0,
                    imageNaturalWidth: 0,
                    imageNaturalHeight: 0,
                    textPosX: null,
                    textPosY: null,
                    imagePosX: null,
                    imagePosY: null,
                    // Шрифты
                    titleFontSize: 'text-xl',
                    titleFontFamily: 'font-sans',
                    titleColor: 'text-gray-900',
                    contentFontSize: 'text-base',
                    contentFontFamily: 'font-sans',
                    contentColor: 'text-gray-700',
                    cardBg: 'bg-white',
                    isNew: true
                };
                
                this.blocks.push(newBlock);
                this.selectedBlockId = newBlock.id;
                this.showSettings = true;
            },
            
            deleteBlock: function(block) {
                if (!confirm('Удалить этот блок?')) return;
                var index = this.blocks.indexOf(block);
                if (index > -1) {
                    this.blocks.splice(index, 1);
                    this.updateOrders();
                    if (this.selectedBlockId === block.id) {
                        this.selectedBlockId = null;
                        this.showSettings = false;
                    }
                }
            },
            
            duplicateBlock: function(block) {
                var newBlock = JSON.parse(JSON.stringify(block));
                newBlock.id = 'new_' + Date.now();
                newBlock.order = this.blocks.length;
                newBlock.isNew = true;
                this.blocks.push(newBlock);
                this.selectedBlockId = newBlock.id;
            },
            
            moveBlockUp: function(block) {
                var index = this.blocks.indexOf(block);
                if (index > 0) {
                    var temp = this.blocks[index];
                    this.blocks[index] = this.blocks[index - 1];
                    this.blocks[index - 1] = temp;
                    this.updateOrders();
                }
            },
            
            moveBlockDown: function(block) {
                var index = this.blocks.indexOf(block);
                if (index < this.blocks.length - 1) {
                    var temp = this.blocks[index];
                    this.blocks[index] = this.blocks[index + 1];
                    this.blocks[index + 1] = temp;
                    this.updateOrders();
                }
            },
            
            updateOrders: function() {
                this.blocks.forEach(function(block, index) {
                    block.order = index;
                });
            },
            
            // Drag & Drop
            onDragStart: function(event, block) {
                this.draggedBlockId = block.id;
                event.dataTransfer.effectAllowed = 'move';
                event.target.classList.add('opacity-50');
            },
            
            onDragOver: function(event, block) {
                event.preventDefault();
                if (this.draggedBlockId && this.draggedBlockId !== block.id) {
                    event.dataTransfer.dropEffect = 'move';
                }
            },
            
            onDrop: function(event, targetBlock) {
                event.preventDefault();
                if (!this.draggedBlockId || this.draggedBlockId === targetBlock.id) return;
                
                var self = this;
                var draggedBlock = this.blocks.find(function(b) { return b.id === self.draggedBlockId; });
                if (!draggedBlock) return;
                
                var draggedIndex = this.blocks.indexOf(draggedBlock);
                var targetIndex = this.blocks.indexOf(targetBlock);
                
                this.blocks.splice(draggedIndex, 1);
                this.blocks.splice(targetIndex, 0, draggedBlock);
                
                this.updateOrders();
            },
            
            onDragEnd: function(event) {
                event.target.classList.remove('opacity-50');
                this.draggedBlockId = null;
            },
            
            // ===== ИЗОБРАЖЕНИЯ =====
            
            uploadImage: function(block) {
                var self = this;
                var input = document.createElement('input');
                input.type = 'file';
                input.accept = 'image/*';
                
                input.onchange = function(e) {
                    var file = e.target.files[0];
                    if (!file) return;
                    
                    var formData = new FormData();
                    formData.append('image', file);
                    formData.append('block_id', block.id);
                    formData.append('page', self.pageType);
                    
                    fetch(self.apiUploadUrl, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': self.csrfToken },
                        body: formData
                    })
                    .then(function(response) { return response.json(); })
                    .then(function(data) {
                        if (data.url) {
                            block.image = data.url;
                            // Сброс crop параметров
                            block.imageCropX = 0;
                            block.imageCropY = 0;
                            block.imageCropWidth = 0;
                            block.imageCropHeight = 0;
                            block.imageNaturalWidth = 0;
                            block.imageNaturalHeight = 0;
                        } else if (data.error) {
                            alert('Ошибка: ' + data.error);
                        }
                    })
                    .catch(function(error) {
                        console.error('Upload error:', error);
                        alert('Ошибка при загрузке');
                    });
                };
                
                input.click();
            },
            
            removeImage: function(block) {
                if (!confirm('Удалить изображение?')) return;
                block.image = '';
                block.imageCropX = 0;
                block.imageCropY = 0;
                block.imageCropWidth = 0;
                block.imageCropHeight = 0;
            },
            
            // ===== CROPPER =====
            
            startCrop: function(block) {
                if (typeof Cropper === 'undefined') {
                    alert('Cropper.js не загружен');
                    return;
                }
                
                this.destroyCropper();
                
                var img = document.querySelector('[data-crop-image="' + block.id + '"]');
                if (!img) return;
                
                this.cropBlockId = block.id;
                
                this.activeCropper = new Cropper(img, {
                    viewMode: 1,
                    autoCropArea: 1,
                    movable: true,
                    zoomable: true,
                    scalable: false,
                    rotatable: false,
                    background: true,
                    responsive: true
                });
            },
            
            applyCrop: function(block) {
                if (!this.activeCropper || this.cropBlockId !== block.id) return;
                
                var data = this.activeCropper.getData(true);
                var imageData = this.activeCropper.getImageData();
                
                block.imageCropX = Math.round(data.x);
                block.imageCropY = Math.round(data.y);
                block.imageCropWidth = Math.round(data.width);
                block.imageCropHeight = Math.round(data.height);
                block.imageNaturalWidth = Math.round(imageData.naturalWidth);
                block.imageNaturalHeight = Math.round(imageData.naturalHeight);
                
                this.destroyCropper();
            },
            
            cancelCrop: function() {
                this.destroyCropper();
            },
            
            destroyCropper: function() {
                if (this.activeCropper) {
                    this.activeCropper.destroy();
                    this.activeCropper = null;
                }
                this.cropBlockId = null;
            },
            
            isCropping: function(block) {
                return this.cropBlockId === block.id;
            },
            
            // ===== СОХРАНЕНИЕ =====
            
            save: function() {
                var self = this;
                this.destroyCropper();
                this.isSaving = true;
                
                var blocksData = this.blocks.map(function(block) {
                    return {
                        id: block.id.toString().indexOf('new_') === 0 ? null : block.id,
                        type: block.type,
                        title: block.title || '',
                        content: block.content || '',
                        image: block.image || '',
                        link_url: block.linkUrl || '',
                        order: block.order,
                        layout: block.layout || 'vertical',
                        image_width: block.imageWidth || 100,
                        image_height: block.imageHeight || 0,
                        image_align: block.imageAlign || 'center',
                        text_align: block.textAlign || 'left',
                        image_crop_x: block.imageCropX || 0,
                        image_crop_y: block.imageCropY || 0,
                        image_crop_width: block.imageCropWidth || 0,
                        image_crop_height: block.imageCropHeight || 0,
                        image_natural_width: block.imageNaturalWidth || 0,
                        image_natural_height: block.imageNaturalHeight || 0,
                        text_pos_x: block.textPosX,
                        text_pos_y: block.textPosY,
                        image_pos_x: block.imagePosX,
                        image_pos_y: block.imagePosY,
                        // Шрифты
                        title_font_size: block.titleFontSize || 'text-xl',
                        title_font_family: block.titleFontFamily || 'font-sans',
                        title_color: block.titleColor || 'text-gray-900',
                        content_font_size: block.contentFontSize || 'text-base',
                        content_font_family: block.contentFontFamily || 'font-sans',
                        content_color: block.contentColor || 'text-gray-700',
                        card_bg: block.cardBg || 'bg-white'
                    };
                });
                
                var payload = {
                    page: this.pageType,
                    blocks: blocksData
                };
                
                if (this.lessonId) {
                    payload.lesson_id = this.lessonId;
                }
                
                fetch(this.apiSaveUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken
                    },
                    body: JSON.stringify(payload)
                })
                .then(function(response) { return response.json(); })
                .then(function(data) {
                    if (data.success) {
                        // Обновляем ID новых блоков
                        if (data.blocks) {
                            data.blocks.forEach(function(saved) {
                                var block = self.blocks.find(function(b) { return b.order === saved.order; });
                                if (block && block.id.toString().indexOf('new_') === 0) {
                                    block.id = saved.id;
                                    block.isNew = false;
                                }
                            });
                        }
                        
                        self.exitEditMode(true);
                        location.reload();
                    } else {
                        alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                        self.isSaving = false;
                    }
                })
                .catch(function(error) {
                    console.error('Save error:', error);
                    alert('Ошибка при сохранении');
                    self.isSaving = false;
                });
            },
            
            // ===== ОПЦИИ ДЛЯ СЕЛЕКТОВ =====
            
            fontSizes: [
                { value: 'text-sm', label: 'Маленький' },
                { value: 'text-base', label: 'Обычный' },
                { value: 'text-lg', label: 'Увеличенный' },
                { value: 'text-xl', label: 'Большой' },
                { value: 'text-2xl', label: 'Очень большой' },
                { value: 'text-3xl', label: 'Огромный' }
            ],
            
            fontFamilies: [
                { value: 'font-sans', label: 'Sans (по умолчанию)' },
                { value: 'font-serif', label: 'Serif' },
                { value: 'font-mono', label: 'Mono' }
            ],
            
            textColors: [
                { value: 'text-gray-900', label: 'Чёрный', hex: '#111827' },
                { value: 'text-gray-700', label: 'Тёмно-серый', hex: '#374151' },
                { value: 'text-gray-500', label: 'Серый', hex: '#6b7280' },
                { value: 'text-white', label: 'Белый', hex: '#ffffff' },
                { value: 'text-blue-600', label: 'Синий', hex: '#2563eb' },
                { value: 'text-green-600', label: 'Зелёный', hex: '#16a34a' },
                { value: 'text-red-600', label: 'Красный', hex: '#dc2626' },
                { value: 'text-yellow-600', label: 'Жёлтый', hex: '#ca8a04' },
                { value: 'text-purple-600', label: 'Фиолетовый', hex: '#9333ea' },
                { value: 'text-pink-600', label: 'Розовый', hex: '#db2777' }
            ],
            
            bgColors: [
                { value: 'bg-white', label: 'Белый', hex: '#ffffff' },
                { value: 'bg-gray-50', label: 'Светло-серый', hex: '#f9fafb' },
                { value: 'bg-gray-100', label: 'Серый', hex: '#f3f4f6' },
                { value: 'bg-gray-800', label: 'Тёмный', hex: '#1f2937' },
                { value: 'bg-blue-50', label: 'Светло-синий', hex: '#eff6ff' },
                { value: 'bg-green-50', label: 'Светло-зелёный', hex: '#f0fdf4' },
                { value: 'bg-yellow-50', label: 'Светло-жёлтый', hex: '#fefce8' },
                { value: 'bg-red-50', label: 'Светло-красный', hex: '#fef2f2' },
                { value: 'bg-purple-50', label: 'Светло-фиолетовый', hex: '#faf5ff' }
            ],
            
            layouts: [
                { value: 'vertical', label: 'Вертикально', icon: '↕️' },
                { value: 'horizontal', label: 'Текст слева', icon: '📝→🖼️' },
                { value: 'horizontal-reverse', label: 'Картинка слева', icon: '🖼️→📝' }
            ],
            
            textAligns: [
                { value: 'left', label: 'По левому краю' },
                { value: 'center', label: 'По центру' },
                { value: 'right', label: 'По правому краю' }
            ]
        };
    });
}
