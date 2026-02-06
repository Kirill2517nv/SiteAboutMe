/**
 * Content Editor - заглушка для совместимости
 * TODO: Переделать lesson_detail.html на использование block-editor.js с Alpine.js
 */

class ContentEditor {
    constructor(config) {
        this.config = config;
        this.container = document.querySelector(config.container);

        // Редактор временно отключён
        // Для редактирования используйте Django Admin
        console.info('ContentEditor: Редактор уроков временно отключён. Используйте Django Admin для редактирования.');
    }
}
