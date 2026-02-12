/**
 * QuizCodeChecker - Async code submission manager with WebSocket support
 *
 * Handles:
 * - WebSocket connection for real-time updates
 * - Code submission via AJAX
 * - UI state management (pending/running/success/failed)
 * - Polling fallback if WebSocket fails
 */
class QuizCodeChecker {
    constructor(quizId, csrfToken) {
        this.quizId = quizId;
        this.csrfToken = csrfToken;
        this.socket = null;
        this.connected = false;
        this.pendingSubmissions = new Map(); // questionId -> submissionId
        this.pollInterval = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;

        // UI callbacks
        this.onStatusChange = null;
        this.onConnectionChange = null; // (status: 'connected'|'disconnected'|'reconnecting'|'polling') => void

        this.init();
    }

    init() {
        this.connectWebSocket();
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/quiz/${this.quizId}/`;

        try {
            this.socket = new WebSocket(wsUrl);

            this.socket.onopen = () => {
                console.log('WebSocket connected');
                this.connected = true;
                this.reconnectAttempts = 0;
                this.stopPolling();
                this._notifyConnection('connected');
            };

            this.socket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };

            this.socket.onclose = (event) => {
                console.log('WebSocket disconnected');
                this.connected = false;
                this._notifyConnection('disconnected');
                this.attemptReconnect();
            };

            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.connected = false;
            };
        } catch (e) {
            console.error('WebSocket connection failed:', e);
            this.startPolling();
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
            this._notifyConnection('reconnecting');
            setTimeout(() => this.connectWebSocket(), delay);
        } else {
            console.log('Max reconnect attempts reached, falling back to polling');
            this._notifyConnection('polling');
            this.startPolling();
        }
    }

    _notifyConnection(status) {
        if (this.onConnectionChange) {
            this.onConnectionChange(status);
        }
    }

    handleMessage(data) {
        if (data.type === 'submission_update') {
            this.handleSubmissionUpdate(data);
        } else if (data.type === 'active_submissions') {
            this.handleActiveSubmissions(data.submissions);
        } else if (data.type === 'help_comment') {
            // Делегируем HelpRequestManager (если инициализирован)
            if (window.helpManager) {
                window.helpManager.handleTeacherReply(data);
            }
        }
    }

    handleSubmissionUpdate(data) {
        const { question_id, status, is_correct, error_log } = data;

        // Update pending map
        if (status === 'success' || status === 'failed' || status === 'error') {
            this.pendingSubmissions.delete(question_id);
        }

        // Trigger UI callback
        if (this.onStatusChange) {
            this.onStatusChange(question_id, status, is_correct, error_log);
        }
    }

    handleActiveSubmissions(submissions) {
        submissions.forEach(sub => {
            this.pendingSubmissions.set(sub.question_id, sub.id);
            if (this.onStatusChange) {
                this.onStatusChange(sub.question_id, sub.status, null, null);
            }
        });
    }

    async submitCode(questionId, code) {
        // Check if already submitting
        if (this.pendingSubmissions.has(questionId)) {
            return { error: 'Код уже на проверке' };
        }

        // Оптимистичная блокировка: помечаем как pending ДО запроса
        this.pendingSubmissions.set(questionId, null);
        if (this.onStatusChange) {
            this.onStatusChange(questionId, 'pending', null, null);
        }

        const url = `/quizzes/${this.quizId}/question/${questionId}/submit/`;

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
                body: JSON.stringify({ code }),
            });

            const data = await response.json();

            if (response.ok) {
                this.pendingSubmissions.set(questionId, data.submission_id);
                return data;
            } else {
                // Снимаем блокировку при ошибке
                this.pendingSubmissions.delete(questionId);
                if (this.onStatusChange) {
                    this.onStatusChange(questionId, null, null, null);
                }
                return { error: data.error || 'Ошибка отправки' };
            }
        } catch (e) {
            console.error('Submit error:', e);
            // Снимаем блокировку при сетевой ошибке
            this.pendingSubmissions.delete(questionId);
            if (this.onStatusChange) {
                this.onStatusChange(questionId, null, null, null);
            }
            return { error: 'Ошибка сети' };
        }
    }

    async checkSubmissionStatus(submissionId) {
        const url = `/quizzes/submission/${submissionId}/status/`;

        try {
            const response = await fetch(url);
            return await response.json();
        } catch (e) {
            console.error('Status check error:', e);
            return null;
        }
    }

    async finishQuiz(answers, force = false) {
        // Check for pending submissions (skip if forced by timer)
        if (!force && this.pendingSubmissions.size > 0) {
            return {
                error: 'Дождитесь завершения проверки всех решений',
                pending_questions: Array.from(this.pendingSubmissions.keys())
            };
        }

        const url = `/quizzes/${this.quizId}/finish/`;

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
                body: JSON.stringify({ answers, force }),
            });

            return await response.json();
        } catch (e) {
            console.error('Finish quiz error:', e);
            return { error: 'Ошибка сети' };
        }
    }

    hasPendingSubmissions() {
        return this.pendingSubmissions.size > 0;
    }

    getPendingQuestions() {
        return Array.from(this.pendingSubmissions.keys());
    }

    // Polling fallback
    startPolling() {
        if (this.pollInterval) return;

        this.pollInterval = setInterval(async () => {
            for (const [questionId, submissionId] of this.pendingSubmissions) {
                const status = await this.checkSubmissionStatus(submissionId);
                if (status && status.status !== 'pending' && status.status !== 'running') {
                    this.handleSubmissionUpdate({
                        question_id: questionId,
                        status: status.status,
                        is_correct: status.is_correct,
                        error_log: status.error_log
                    });
                }
            }
        }, 2000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    destroy() {
        this.stopPolling();
        if (this.socket) {
            this.socket.close();
        }
    }
}

// Export for module systems, also attach to window for direct use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = QuizCodeChecker;
}
window.QuizCodeChecker = QuizCodeChecker;
