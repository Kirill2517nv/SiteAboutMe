/**
 * HelpRequestManager - UI для системы запросов помощи (ученик)
 *
 * Управляет:
 * - Gutter click на CodeMirror -> toggle тред к строке (история + форма)
 * - Панель помощи (только общие комментарии)
 * - AJAX-взаимодействие с /help/ endpoint
 * - Отображение ответов учителя (inline line widgets)
 * - Подсказка о кликабельности номеров строк
 */
class HelpRequestManager {
    constructor(quizId, csrfToken, editors) {
        this.quizId = quizId;
        this.csrfToken = csrfToken;
        this.editors = editors; // { questionId: CodeMirror instance }
        this.helpData = {};    // { questionId: { help_request_id, status, comments[] } }
        this.openThreads = {}; // { "questionId_lineNumber": widget } — открытые треды
        this._markedLines = {}; // { questionId: Set of 0-based line indices }

        this.init();
    }

    init() {
        // Привязываем gutter click ко всем code-редакторам
        Object.entries(this.editors).forEach(([questionId, cm]) => {
            cm.on('gutterClick', (cm, line) => {
                this.toggleLineThread(questionId, line + 1, cm.getValue());
                this._hideHint(questionId);
            });
        });

        // Показываем подсказку через 1с (если не показывали ранее)
        this._showHints();

        // Загружаем данные и маркеры для всех вопросов
        this._loadInitialMarkers();
    }

    /**
     * Загружает help data для всех вопросов и ставит маркеры строк.
     */
    async _loadInitialMarkers() {
        const questionIds = Object.keys(this.editors);
        await Promise.all(questionIds.map(qId => this.loadHelpData(qId)));
    }

    // ===================== ПОДСКАЗКА (Фикс 1) =====================

    _showHints() {
        if (sessionStorage.getItem('help_hint_shown')) return;

        setTimeout(() => {
            Object.keys(this.editors).forEach(qId => {
                const hint = document.getElementById(`gutter-hint-${qId}`);
                if (hint) {
                    hint.classList.remove('hidden');
                    hint.classList.add('animate-fade-in');
                }
            });
            // Авто-скрытие через 8с
            setTimeout(() => this._hideAllHints(), 8000);
        }, 1000);
    }

    _hideHint(questionId) {
        const hint = document.getElementById(`gutter-hint-${questionId}`);
        if (hint) hint.classList.add('hidden');
        sessionStorage.setItem('help_hint_shown', '1');
    }

    _hideAllHints() {
        Object.keys(this.editors).forEach(qId => this._hideHint(qId));
    }

    // ===================== МАРКЕРЫ СТРОК =====================

    /**
     * Обновляет визуальные маркеры строк, к которым есть комментарии.
     * Добавляет CSS-класс line-has-comments на строки с тредами,
     * убирает с тех, где комментариев больше нет.
     */
    _updateLineMarkers(questionId) {
        const cm = this.editors[questionId];
        if (!cm) return;

        const data = this.helpData[questionId];
        const comments = (data && data.comments) ? data.comments : [];

        // Собираем Set строк (0-based), к которым есть комментарии
        const linesWithComments = new Set();
        comments.forEach(c => {
            if (c.line_number) {
                linesWithComments.add(c.line_number - 1); // API: 1-based → CM: 0-based
            }
        });

        const prevMarked = this._markedLines[questionId] || new Set();

        // Убираем класс со строк, где комментариев больше нет
        prevMarked.forEach(line => {
            if (!linesWithComments.has(line)) {
                cm.removeLineClass(line, 'wrap', 'line-has-comments');
            }
        });

        // Добавляем класс на новые строки с комментариями
        linesWithComments.forEach(line => {
            if (!prevMarked.has(line)) {
                cm.addLineClass(line, 'wrap', 'line-has-comments');
            }
        });

        this._markedLines[questionId] = linesWithComments;
    }

    // ===================== ДАННЫЕ =====================

    /**
     * Загружает данные help request для вопроса.
     * @param {boolean} markRead — если true, сбрасывает has_unread_for_student на сервере
     */
    async loadHelpData(questionId, markRead = false) {
        try {
            const url = `/quizzes/${this.quizId}/question/${questionId}/help/`
                + (markRead ? '?mark_read=1' : '');
            const response = await fetch(url, { credentials: 'same-origin' });
            if (!response.ok) return null;
            const data = await response.json();
            this.helpData[questionId] = data;
            this._updateLineMarkers(questionId);
            return data;
        } catch (e) {
            console.error('Failed to load help data:', e);
            return null;
        }
    }

    /**
     * Отправляет комментарий
     */
    async sendComment(questionId, text, lineNumber, codeSnapshot) {
        try {
            const response = await fetch(
                `/quizzes/${this.quizId}/question/${questionId}/help/`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        text: text,
                        line_number: lineNumber || null,
                        code_snapshot: codeSnapshot || null,
                    }),
                }
            );
            const data = await response.json();
            if (response.ok) {
                this.helpData[questionId] = data;
                this._updateLineMarkers(questionId);
                return data;
            }
            return { error: data.error || 'Ошибка отправки' };
        } catch (e) {
            console.error('Failed to send comment:', e);
            return { error: 'Ошибка сети' };
        }
    }

    // ===================== TOGGLE LINE THREAD (Фикс 4) =====================

    /**
     * Переключает тред к строке: клик открывает, повторный — закрывает.
     * Тред = история комментариев к строке + форма нового комментария.
     */
    async toggleLineThread(questionId, lineNumber, codeSnapshot) {
        const cm = this.editors[questionId];
        if (!cm) return;

        const threadKey = `${questionId}_${lineNumber}`;

        // Если тред уже открыт — закрываем (toggle)
        if (this.openThreads[threadKey]) {
            this.openThreads[threadKey].clear();
            delete this.openThreads[threadKey];
            return;
        }

        // Подгружаем данные если ещё не загружены (с mark_read)
        if (!this.helpData[questionId]) {
            await this.loadHelpData(questionId, true);
        }

        // Строим тред: существующие комментарии + форма
        const threadEl = this._createThreadElement(questionId, lineNumber, codeSnapshot);

        const widget = cm.addLineWidget(lineNumber - 1, threadEl, {
            coverGutter: false,
            noHScroll: true,
        });
        this.openThreads[threadKey] = widget;

        // Фокус на textarea
        const textarea = threadEl.querySelector('textarea');
        if (textarea) textarea.focus();
    }

    /**
     * Создаёт DOM полного треда: история + форма ввода.
     */
    _createThreadElement(questionId, lineNumber, codeSnapshot) {
        const container = document.createElement('div');
        container.style.cssText = 'background: #1e293b; border: 1px solid #f59e0b; border-radius: 8px; margin: 4px 8px; padding: 0; overflow: hidden;';

        // --- Заголовок ---
        const header = document.createElement('div');
        header.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #0f172a; border-bottom: 1px solid #334155;';

        const title = document.createElement('span');
        title.style.cssText = 'color: #f59e0b; font-size: 12px; font-weight: 600;';
        title.textContent = `Строка ${lineNumber}`;

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.innerHTML = '&times;';
        closeBtn.style.cssText = 'background: none; border: none; color: #64748b; font-size: 18px; cursor: pointer; line-height: 1; padding: 0 4px;';
        closeBtn.onclick = () => {
            const threadKey = `${questionId}_${lineNumber}`;
            if (this.openThreads[threadKey]) {
                this.openThreads[threadKey].clear();
                delete this.openThreads[threadKey];
            }
        };

        header.appendChild(title);
        header.appendChild(closeBtn);
        container.appendChild(header);

        // --- Существующие комментарии ---
        const data = this.helpData[questionId];
        const lineComments = (data && data.comments)
            ? data.comments.filter(c => c.line_number === lineNumber)
            : [];

        if (lineComments.length > 0) {
            const commentsDiv = document.createElement('div');
            commentsDiv.style.cssText = 'max-height: 200px; overflow-y: auto; padding: 8px 12px;';
            commentsDiv.className = 'thread-comments';

            lineComments.forEach((c, idx) => {
                const item = document.createElement('div');
                item.style.cssText = 'margin-bottom: 8px; padding-bottom: 8px;' +
                    (idx < lineComments.length - 1 ? ' border-bottom: 1px solid #334155;' : '');

                const itemHeader = document.createElement('div');
                itemHeader.style.cssText = 'display: flex; align-items: center; gap: 6px; margin-bottom: 3px;';

                const author = document.createElement('span');
                author.style.cssText = `font-size: 12px; font-weight: 600; color: ${c.is_teacher ? '#34d399' : '#fbbf24'};`;
                author.textContent = c.author;

                const time = document.createElement('span');
                time.style.cssText = 'font-size: 11px; color: #64748b;';
                time.textContent = new Date(c.created_at).toLocaleString('ru-RU', {
                    hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short'
                });

                itemHeader.appendChild(author);
                itemHeader.appendChild(time);

                const text = document.createElement('div');
                text.style.cssText = 'font-size: 13px; color: #e2e8f0; white-space: pre-wrap;';
                text.textContent = c.text;

                item.appendChild(itemHeader);
                item.appendChild(text);
                commentsDiv.appendChild(item);
            });

            container.appendChild(commentsDiv);
        }

        // --- Форма нового комментария ---
        const formDiv = document.createElement('div');
        formDiv.style.cssText = 'padding: 8px 12px; border-top: 1px solid #334155;';

        const textarea = document.createElement('textarea');
        textarea.rows = 2;
        textarea.placeholder = lineComments.length > 0 ? 'Продолжить диалог...' : 'Опишите, что не понятно...';
        textarea.style.cssText = 'width: 100%; background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px; padding: 8px; font-size: 13px; resize: vertical; font-family: inherit;';
        formDiv.appendChild(textarea);

        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display: flex; gap: 8px; margin-top: 6px; justify-content: flex-end;';

        const sendBtn = document.createElement('button');
        sendBtn.type = 'button';
        sendBtn.textContent = 'Отправить';
        sendBtn.style.cssText = 'padding: 5px 14px; background: #f59e0b; color: #1e293b; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer;';
        sendBtn.onclick = async () => {
            const text = textarea.value.trim();
            if (!text) return;
            if (text.length > 10000) {
                alert(`Комментарий слишком длинный (${text.length} символов). Максимум 10000 символов.`);
                return;
            }
            sendBtn.disabled = true;
            sendBtn.textContent = 'Отправка...';
            const result = await this.sendComment(questionId, text, lineNumber, codeSnapshot);
            if (result.error) {
                alert(result.error);
                sendBtn.disabled = false;
                sendBtn.textContent = 'Отправить';
            } else {
                // Переоткрываем тред с обновлёнными данными
                const threadKey = `${questionId}_${lineNumber}`;
                if (this.openThreads[threadKey]) {
                    this.openThreads[threadKey].clear();
                    delete this.openThreads[threadKey];
                }
                this.toggleLineThread(questionId, lineNumber, codeSnapshot);
                this.renderHelpPanel(questionId);
            }
        };

        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault();
                sendBtn.click();
            }
            if (e.key === 'Escape') {
                const threadKey = `${questionId}_${lineNumber}`;
                if (this.openThreads[threadKey]) {
                    this.openThreads[threadKey].clear();
                    delete this.openThreads[threadKey];
                }
            }
        });

        btnRow.appendChild(sendBtn);
        formDiv.appendChild(btnRow);
        container.appendChild(formDiv);

        return container;
    }

    // ===================== РЕНДЕР (Фикс 3) =====================

    /**
     * Отрисовывает/обновляет панель помощи — ТОЛЬКО общие комментарии.
     * Line-комментарии показываются только как line widgets.
     */
    renderHelpPanel(questionId) {
        const panel = document.getElementById(`help-panel-${questionId}`);
        if (!panel) return;

        const data = this.helpData[questionId];
        const commentsContainer = panel.querySelector('.help-comments-list');

        if (!commentsContainer) return;

        const allComments = (data && data.comments) ? data.comments : [];
        const generalComments = allComments.filter(c => !c.line_number);
        const hasLineComments = allComments.some(c => c.line_number);

        commentsContainer.innerHTML = '';

        if (generalComments.length === 0) {
            let hint = 'Нет комментариев. Кликните на номер строки или напишите общий вопрос ниже.';
            if (hasLineComments) {
                hint = 'Комментарии к строкам отображаются в коде выше. Здесь — только общие вопросы.';
            }
            commentsContainer.innerHTML = `<p class="text-gray-400 text-sm italic">${hint}</p>`;
            return;
        }

        generalComments.forEach(c => {
            const div = document.createElement('div');
            div.className = `p-3 rounded-lg mb-2 ${c.is_teacher ? 'bg-green-50 border border-green-200' : 'bg-gray-50 border border-gray-200'}`;

            const header = document.createElement('div');
            header.className = 'flex items-center gap-2 mb-1';
            header.innerHTML = `
                <span class="text-xs font-semibold ${c.is_teacher ? 'text-green-700' : 'text-amber-700'}">${this._escapeHtml(c.author)}</span>
                <span class="text-xs text-gray-400 ml-auto">${new Date(c.created_at).toLocaleString('ru-RU', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}</span>
            `;

            const text = document.createElement('div');
            text.className = 'text-sm text-gray-700 whitespace-pre-wrap';
            text.textContent = c.text;

            div.appendChild(header);
            div.appendChild(text);
            commentsContainer.appendChild(div);
        });

        commentsContainer.scrollTop = commentsContainer.scrollHeight;
    }

    /**
     * Переключает видимость панели помощи
     */
    async toggleHelpPanel(questionId) {
        const panel = document.getElementById(`help-panel-${questionId}`);
        if (!panel) return;

        const isHidden = panel.classList.contains('hidden');
        if (isHidden) {
            panel.classList.remove('hidden');
            await this.loadHelpData(questionId, true);
            this.renderHelpPanel(questionId);
        } else {
            panel.classList.add('hidden');
        }
    }

    /**
     * Раскрывает все line-треды для вопроса (без toggle — только открытие).
     */
    openAllLineThreads(questionId) {
        const data = this.helpData[questionId];
        if (!data || !data.comments) return;
        const cm = this.editors[questionId];
        if (!cm) return;

        const lineNumbers = new Set();
        data.comments.forEach(c => {
            if (c.line_number) lineNumbers.add(c.line_number);
        });

        lineNumbers.forEach(lineNum => {
            const threadKey = `${questionId}_${lineNum}`;
            if (!this.openThreads[threadKey]) {
                this.toggleLineThread(questionId, lineNum, cm.getValue());
            }
        });
    }

    /**
     * Отправляет общий комментарий из панели
     */
    async sendGeneralComment(questionId) {
        const panel = document.getElementById(`help-panel-${questionId}`);
        if (!panel) return;

        const textarea = panel.querySelector('.help-general-textarea');
        if (!textarea) return;

        const text = textarea.value.trim();
        if (!text) return;
        if (text.length > 10000) {
            alert(`Комментарий слишком длинный (${text.length} символов). Максимум 10000 символов.`);
            return;
        }

        const sendBtn = panel.querySelector('.help-send-btn');
        if (sendBtn) {
            sendBtn.disabled = true;
            sendBtn.textContent = 'Отправка...';
        }

        const cm = this.editors[questionId];
        const code = cm ? cm.getValue() : null;

        const result = await this.sendComment(questionId, text, null, code);

        if (result.error) {
            alert(result.error);
        } else {
            textarea.value = '';
            this.renderHelpPanel(questionId);
        }

        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.textContent = 'Отправить';
        }
    }

    /**
     * Обрабатывает ответ учителя, пришедший через WebSocket
     */
    handleTeacherReply(data) {
        const questionId = data.question_id;

        if (!this.helpData[questionId]) {
            this.helpData[questionId] = { comments: [] };
        }
        if (data.comment) {
            this.helpData[questionId].comments.push(data.comment);
        }
        if (data.status) {
            this.helpData[questionId].status = data.status;
        }

        // Обновляем маркеры строк и панель (общие комментарии)
        this._updateLineMarkers(questionId);
        this.renderHelpPanel(questionId);

        // Если ответ к строке и тред открыт — переоткрываем с новыми данными
        if (data.comment && data.comment.line_number) {
            const threadKey = `${questionId}_${data.comment.line_number}`;
            if (this.openThreads[threadKey]) {
                const cm = this.editors[questionId];
                this.openThreads[threadKey].clear();
                delete this.openThreads[threadKey];
                this.toggleLineThread(questionId, data.comment.line_number, cm ? cm.getValue() : '');
            }
        }

        // Визуальная пульсация кнопки
        const btn = document.getElementById(`help-btn-${questionId}`);
        if (btn) {
            btn.classList.add('text-amber-600');
            btn.style.animation = 'pulse 1s ease-in-out 3';
            setTimeout(() => { btn.style.animation = ''; }, 3000);
        }
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = HelpRequestManager;
}
window.HelpRequestManager = HelpRequestManager;
