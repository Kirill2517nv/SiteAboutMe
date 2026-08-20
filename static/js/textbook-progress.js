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

    // --- Учёт времени чтения ---------------------------------------------
    // Считаем только время с активной вкладкой: свёрнутое окно или переход на
    // другую вкладку паузят счётчик, иначе в отчёте у всех были бы часы чтения.
    const timeUrl = root.dataset.timeUrl;
    if (timeUrl) {
        const FLUSH_EVERY_MS = 30000;
        let activeMs = 0;
        let lastTick = document.visibilityState === 'visible' ? Date.now() : null;

        function accumulate() {
            if (lastTick !== null) {
                activeMs += Date.now() - lastTick;
                lastTick = Date.now();
            }
        }

        function flush(useBeacon) {
            accumulate();
            const seconds = Math.floor(activeMs / 1000);
            if (seconds < 5) return; // мелочь не шлём, чтобы не сорить запросами
            activeMs -= seconds * 1000;

            const body = new FormData();
            body.append('seconds', seconds);
            body.append('csrfmiddlewaretoken', csrf);
            if (useBeacon && navigator.sendBeacon) {
                navigator.sendBeacon(timeUrl, body);
            } else {
                fetch(timeUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrf },
                    credentials: 'same-origin',
                    body: body,
                }).catch(function () { activeMs += seconds * 1000; });
            }
        }

        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible') {
                lastTick = Date.now();
            } else {
                accumulate();
                lastTick = null;
                flush(true);
            }
        });
        setInterval(function () { flush(false); }, FLUSH_EVERY_MS);
        window.addEventListener('pagehide', function () { flush(true); });
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
