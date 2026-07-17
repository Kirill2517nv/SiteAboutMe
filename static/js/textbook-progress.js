/*
 * Трекинг прогресса чтения статьи учебника.
 * При открытии статьи сервер уже создал ArticleProgress со статусом «читается».
 * Здесь: когда ученик долистывает до конца статьи (#article-end становится
 * виден), отправляем beacon-POST → статус «прочитано».
 */
(function () {
    'use strict';

    const root = document.getElementById('article-root');
    const endMarker = document.getElementById('article-end');
    if (!root || !endMarker) return;
    if (root.dataset.authenticated !== '1') return; // прогресс только для авторизованных

    const readUrl = root.dataset.readUrl;
    const csrf = root.dataset.csrf;
    if (!readUrl) return;

    let sent = false;

    function markRead() {
        if (sent) return;
        sent = true;
        fetch(readUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin',
        })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data) return;
                const badge = document.getElementById('progress-badge');
                if (badge && data.status === 'read') {
                    badge.textContent = 'Прочитано';
                    badge.dataset.status = 'read';
                }
            })
            .catch(function () { sent = false; }); // разрешим повтор при сбое сети
    }

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    markRead();
                    observer.disconnect();
                }
            });
        }, { threshold: 0.1 });
        observer.observe(endMarker);
    } else {
        // Фолбэк: отметить при выгрузке страницы
        window.addEventListener('beforeunload', markRead);
    }
})();
