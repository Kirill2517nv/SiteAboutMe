/**
 * EGE Timer & Tracking modules
 *
 * EgeTimer — countdown timer for exam mode (235 min)
 * TaskTimeTracker — tracks time spent on each task
 * EgeAnswerStore — localStorage persistence for answers
 */


/**
 * EgeTimer — exam countdown (only used in exam mode).
 *
 * Saves startedAt in localStorage so page refresh doesn't reset the clock.
 * Calls onTick(display, isCritical) every second.
 * Calls onExpire() when time runs out.
 */
class EgeTimer {
    constructor(quizId, totalMinutes, onTick, onExpire) {
        this.quizId = quizId;
        this.totalSeconds = totalMinutes * 60;
        this.onTick = onTick;
        this.onExpire = onExpire;
        this.intervalId = null;
        this.storageKey = `ege_timer_${quizId}`;
    }

    start() {
        // Restore or set start time
        let startedAt = localStorage.getItem(this.storageKey);
        if (!startedAt) {
            startedAt = Date.now().toString();
            localStorage.setItem(this.storageKey, startedAt);
        }
        this.startedAt = parseInt(startedAt, 10);
        this.tick();
        this.intervalId = setInterval(() => this.tick(), 1000);
    }

    tick() {
        const elapsed = Math.floor((Date.now() - this.startedAt) / 1000);
        const remaining = Math.max(0, this.totalSeconds - elapsed);

        const minutes = Math.floor(remaining / 60);
        const seconds = remaining % 60;
        const display = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        const isCritical = remaining < 300; // < 5 min

        if (this.onTick) this.onTick(display, isCritical);

        if (remaining <= 0) {
            this.stop();
            if (this.onExpire) this.onExpire();
        }
    }

    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        localStorage.removeItem(this.storageKey);
    }
}


/**
 * TaskTimeTracker — tracks seconds spent on each task.
 *
 * On task switch: sends accumulated delta to server.
 * Also sends periodically every 30s for long-running tasks.
 */
class TaskTimeTracker {
    constructor(quizId, csrfToken) {
        this.quizId = quizId;
        this.csrfToken = csrfToken;
        this.currentTaskId = null;
        this.taskStartedAt = null;
        this.periodicId = null;
    }

    startTask(taskId) {
        this.currentTaskId = taskId;
        this.taskStartedAt = Date.now();

        // Periodic save every 30s
        this.stopPeriodic();
        this.periodicId = setInterval(() => this.sendDelta(), 30000);
    }

    stopTask(taskId) {
        if (this.currentTaskId === taskId) {
            this.sendDelta();
            this.stopPeriodic();
            this.currentTaskId = null;
            this.taskStartedAt = null;
        }
    }

    sendDelta() {
        if (!this.currentTaskId || !this.taskStartedAt) return;

        const seconds = Math.floor((Date.now() - this.taskStartedAt) / 1000);
        if (seconds <= 0) return;

        // Reset start for next interval
        this.taskStartedAt = Date.now();

        // Fire-and-forget POST
        fetch(`/ege/${this.quizId}/save-time/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
            body: JSON.stringify({ question_id: this.currentTaskId, seconds }),
        }).catch(() => {}); // Non-critical
    }

    stopPeriodic() {
        if (this.periodicId) {
            clearInterval(this.periodicId);
            this.periodicId = null;
        }
    }

    destroy() {
        this.sendDelta();
        this.stopPeriodic();
    }
}


/**
 * EgeAnswerStore — localStorage persistence for EGE answers.
 *
 * Хранит ответы пользователя в localStorage браузера,
 * чтобы они не пропали при перезагрузке страницы.
 */
class EgeAnswerStore {
    constructor(quizId) {
        // Уникальный ключ для каждого варианта, чтобы ответы не смешивались
        this.key = `ege_answers_${quizId}`;
    }

    load() {
        try {
            const raw = localStorage.getItem(this.key);
            // Если ничего нет — пустой объект
            if (!raw) return {};
            // Парсим JSON обратно в объект
            const parsed = JSON.parse(raw);
            // Защита: если parsed — не объект (кто-то испортил данные), возвращаем {}
            if (typeof parsed !== 'object' || parsed === null) return {};
            return parsed;
        } catch (e) {
            // JSON повреждён — начинаем с чистого листа
            return {};
        }
    }

    save(answers) {
        localStorage.setItem(this.key, JSON.stringify(answers));
    }

    clear() {
        localStorage.removeItem(this.key);
    }
}


// Export to window
window.EgeTimer = EgeTimer;
window.TaskTimeTracker = TaskTimeTracker;
window.EgeAnswerStore = EgeAnswerStore;
