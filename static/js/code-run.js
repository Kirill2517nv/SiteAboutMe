// «Запустить» в тренажёре ЕГЭ: прогон кода без оценки (quizzes.views.run_code_view).
// Код и язык берёт у страницы – её компонент обязан иметь codeOf(key) и
// langOf(key). Все имена с префиксом run: Alpine ищет поле через общий прокси,
// и одноимённое поле страницы перекрыло бы наше.
function codeRunner(questionId, key) {
    return {
        runStdin: '',
        runBusy: false,
        runResult: null,    // {output, error, cpu_time_ms, memory_kb}
        runError: '',
        _runToken: null,
        _runTimer: null,

        destroy() { clearInterval(this._runTimer); },

        async run() {
            const code = this.codeOf(key);
            if (!code.trim() || this.runBusy) return;
            this.runBusy = true;
            this.runError = '';
            this.runResult = null;
            try {
                const resp = await fetch(`/quizzes/question/${questionId}/run/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': runCsrf() },
                    body: JSON.stringify({ code, language: this.langOf(key), stdin: this.runStdin }),
                });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.error || 'Не удалось запустить');
                this._runToken = data.token;
                this._runPolls = 0;
                this._runTimer = setInterval(() => this._runPoll(), 1000);
            } catch (e) {
                this.runError = e.message;
                this.runBusy = false;
            }
        },

        async _runPoll() {
            try {
                const resp = await fetch(`/quizzes/run/${this._runToken}/`);
                const data = await resp.json();
                if (data.status !== 'done') {
                    // Контейнер живёт меньше минуты; дольше – значит очередь
                    // проверки стоит, и ждать молча бессмысленно.
                    if (++this._runPolls < 120) return;
                    throw new Error();
                }
                this.runResult = data;
            } catch (e) {
                this.runError = 'Не удалось получить результат запуска';
            }
            clearInterval(this._runTimer);
            this.runBusy = false;
        },

        runStop() {
            if (!this._runToken) return;
            fetch(`/quizzes/run/${this._runToken}/stop/`, {
                method: 'POST', headers: { 'X-CSRFToken': runCsrf() },
            }).catch(() => {});
        },

        runMetrics() {
            const r = this.runResult;
            if (!r) return '';
            const parts = [];
            if (r.cpu_time_ms != null) {
                parts.push(r.cpu_time_ms >= 1000 ? (r.cpu_time_ms / 1000).toFixed(2) + ' с'
                    : (r.cpu_time_ms < 1 ? '< 1 мс' : Math.round(r.cpu_time_ms) + ' мс'));
            }
            if (r.memory_kb != null) {
                parts.push(r.memory_kb < 1024 ? r.memory_kb + ' КБ' : (r.memory_kb / 1024).toFixed(1) + ' МБ');
            }
            return parts.join(' · ');
        },
    };
}

function runCsrf() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : (document.querySelector('[name=csrfmiddlewaretoken]')?.value || '');
}
