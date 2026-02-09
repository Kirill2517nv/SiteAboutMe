/**
 * NotificationManager - Badge notifications via WebSocket with polling fallback
 * + Dropdown with teacher replies for students
 */
class NotificationManager {
    constructor() {
        this.socket = null;
        this.connected = false;
        this.pollInterval = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        this.badgeEl = document.getElementById('help-badge-global');

        this.init();
    }

    init() {
        this.connectWebSocket();
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/notifications/`;

        try {
            this.socket = new WebSocket(wsUrl);

            this.socket.onopen = () => {
                this.connected = true;
                this.reconnectAttempts = 0;
                this.stopPolling();
            };

            this.socket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'unread_count_update' || data.type === 'help_notification') {
                    this.updateBadge(data.unread_count);
                }
            };

            this.socket.onclose = () => {
                this.connected = false;
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    setTimeout(() => this.connectWebSocket(), 2000 * this.reconnectAttempts);
                } else {
                    this.startPolling();
                }
            };

            this.socket.onerror = () => {
                this.connected = false;
            };
        } catch (e) {
            this.startPolling();
        }
    }

    updateBadge(count) {
        if (!this.badgeEl) return;
        if (count > 0) {
            this.badgeEl.textContent = count > 99 ? '99+' : count;
            this.badgeEl.classList.remove('hidden');
        } else {
            this.badgeEl.classList.add('hidden');
        }
    }

    startPolling() {
        if (this.pollInterval) return;
        this.poll();
        this.pollInterval = setInterval(() => this.poll(), 30000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async poll() {
        try {
            const response = await fetch('/quizzes/help-requests/unread-count/');
            if (response.ok) {
                const data = await response.json();
                this.updateBadge(data.unread_count);
            }
        } catch (e) {
            // Ignore polling errors
        }
    }

    /**
     * Загружает и рендерит dropdown со списком уведомлений (для ученика)
     */
    async loadDropdown() {
        const container = document.getElementById('notif-dropdown-list');
        if (!container) return;

        container.innerHTML = '<div class="px-4 py-6 text-center text-sm text-gray-400">Загрузка...</div>';

        try {
            const response = await fetch('/quizzes/help-requests/my-notifications/');
            if (!response.ok) return;
            const data = await response.json();

            container.innerHTML = '';

            if (!data.notifications || data.notifications.length === 0) {
                container.innerHTML = '<div class="px-4 py-8 text-center text-sm text-gray-400">Нет новых уведомлений</div>';
                return;
            }

            data.notifications.forEach(n => {
                const link = document.createElement('a');
                link.href = `/quizzes/${n.quiz_id}/?open_help=${n.question_id}#question-${n.question_id}`;
                link.className = 'block px-4 py-3 hover:bg-amber-50 border-b border-gray-100 transition-colors';

                const title = document.createElement('div');
                title.className = 'text-sm font-medium text-gray-900 truncate';
                title.textContent = n.question_title;

                const meta = document.createElement('div');
                meta.className = 'text-xs text-gray-500 mt-0.5';
                meta.textContent = n.quiz_title;

                const preview = document.createElement('div');
                preview.className = 'text-xs text-green-700 mt-1 truncate';
                preview.textContent = n.teacher_name ? `${n.teacher_name}: ${n.preview}` : n.preview;

                const time = document.createElement('div');
                time.className = 'text-xs text-gray-400 mt-1';
                time.textContent = this._timeAgo(n.updated_at);

                link.appendChild(title);
                link.appendChild(meta);
                if (n.preview) link.appendChild(preview);
                link.appendChild(time);
                container.appendChild(link);
            });
        } catch (e) {
            container.innerHTML = '<div class="px-4 py-6 text-center text-sm text-red-400">Ошибка загрузки</div>';
        }
    }

    _timeAgo(isoStr) {
        const diff = Date.now() - new Date(isoStr).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'только что';
        if (mins < 60) return `${mins} мин. назад`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours} ч. назад`;
        const days = Math.floor(hours / 24);
        return `${days} дн. назад`;
    }
}

// Auto-init on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    window.notificationManager = new NotificationManager();
});
