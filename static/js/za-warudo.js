// Пасхалка «Заваруду» (zawarudo): остановка времени на работе с таймером.
// Партиал – templates/quizzes/_za_warudo.html, контекст – classwork.za_warudo_context.
// Грузится в pre_alpine_js: Alpine стартует сразу после своего тега, и
// компонент из extra_js не успевает.
//
// Кнопка живёт в партиале, а событие `za-warudo` ловят сами страницы: они
// знают, где у них дедлайн (ege_practice, classwork_work, EgeTimer варианта),
// и сдвигают его ровно на выданные секунды. Показ таймера на это время
// замирает: сервер уже продлил дедлайн, и без заморозки число прыгнуло бы
// вверх, хотя время ещё «стоит».

function zaWarudo(cfg) {
    return {
        kind: cfg.kind,
        objId: cfg.objId,
        seconds: cfg.seconds,
        url: cfg.url,
        csrf: cfg.csrf,
        readyAt: cfg.readyAt ? Date.parse(cfg.readyAt) : 0,
        now: Date.now(),
        busy: false,
        error: '',

        // Сцена: 1 – вспышка и надпись, 2 – остаток секунд у краёв, 3 – затухание.
        sceneShow: false,
        scenePhase: 0,
        sceneCounter: 0,
        sceneToast: '',

        _tick: null,
        _phase1: null,
        _fade: null,
        _end: null,
        _count: null,

        init() {
            this._tick = setInterval(() => { this.now = Date.now(); }, 1000);
        },

        destroy() {
            clearInterval(this._tick);
            clearInterval(this._count);
            clearTimeout(this._phase1);
            clearTimeout(this._fade);
            clearTimeout(this._end);
        },

        get cooldownLeft() {
            return this.readyAt > this.now
                ? Math.ceil((this.readyAt - this.now) / 1000) : 0;
        },

        get ready() {
            return !this.busy && this.cooldownLeft === 0;
        },

        get label() {
            if (this.cooldownLeft > 0) {
                const hours = Math.floor(this.cooldownLeft / 3600);
                const minutes = Math.floor((this.cooldownLeft % 3600) / 60);
                return 'Остановка времени через '
                    + String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');
            }
            return '⏸ ZA WARUDO · ' + this.seconds + ' с';
        },

        async use() {
            if (!this.ready) return;
            this.busy = true;
            this.error = '';
            try {
                const resp = await fetch(this.url, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': this.csrf,
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: new URLSearchParams({kind: this.kind, id: this.objId}),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) {
                    if (data.ready_at) this.readyAt = Date.parse(data.ready_at) || 0;
                    this.error = this._errorText(resp.status, data.error);
                    return;
                }
                // Следующее применение будет длиннее на секунду – кнопка
                // показывает именно его, а кулдаун тикает с готового ответа.
                this.seconds = data.next_seconds || this.seconds;
                this.readyAt = data.ready_at ? (Date.parse(data.ready_at) || 0) : 0;
                window.dispatchEvent(new CustomEvent('za-warudo', {
                    detail: {seconds: data.seconds, deadline: data.deadline},
                }));
                this.play(data.seconds);
            } catch (e) {
                this.error = 'Сеть не ответила – попробуйте ещё раз.';
            } finally {
                this.busy = false;
            }
        },

        _errorText(status, code) {
            if (status === 403) return 'Остановка времени здесь не разрешена.';
            if (status === 404) return 'Работа не найдена.';
            if (status === 409 && code === 'cooldown') return 'Способность ещё перезаряжается.';
            if (status === 409) return 'Работа уже не идёт – останавливать нечего.';
            return 'Не получилось – попробуйте ещё раз.';
        },

        // Секрет нашёлся: страница шлёт тост, сцена играет 2,5 с.
        playScene(detail) {
            this.play(detail.seconds || 2.5, detail.toast || '');
        },

        play(seconds, toast) {
            const total = Math.max(1, Number(seconds) || 5) * 1000;
            clearInterval(this._count);
            clearTimeout(this._phase1);
            clearTimeout(this._fade);
            clearTimeout(this._end);

            // Счётчик – остаток до конца остановки, а не «минус один в
            // секунду с начала фазы 2»: тот стартовал на 1,5 с позже и при
            // исчезновении сцены показывал ещё 2.
            const endAt = Date.now() + total;
            const count = () => {
                this.sceneCounter = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
            };
            this.sceneToast = toast || '';
            count();
            this.scenePhase = 1;
            this.sceneShow = true;
            this._count = setInterval(count, 200);

            this._phase1 = setTimeout(() => { this.scenePhase = 2; }, 1500);
            this._fade = setTimeout(() => { this.scenePhase = 3; }, Math.max(0, total - 500));
            this._end = setTimeout(() => {
                clearInterval(this._count);
                this.sceneShow = false;
                this.scenePhase = 0;
                this.sceneToast = '';
            }, total);
        },
    };
}

// Секрет «Заваруду»: сдать работу в последние 30 секунд. Зовётся со страницы
// перед сдачей, ошибка или молчание запроса сдачу не срывают, поэтому здесь
// нет ни исключений наружу, ни ожидания дольше 1,5 с.
async function zaWarudoHunt(url, csrf, left) {
    if (!(left > 0 && left <= 30)) return null;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1500);
    let data = null;
    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: {'X-CSRFToken': csrf},
            signal: controller.signal,
        });
        data = await resp.json();
    } catch (e) {
        return null;
    } finally {
        clearTimeout(timer);
    }
    // Сцену видят только те, кому хватит времени до сдачи: на четырёх
    // секундах две с половиной – это половина остатка. Сбой самого показа
    // сдачу не срывает: он здесь ради пасхалки, а не наоборот.
    if (data && data.new && left >= 4) {
        try {
            window.dispatchEvent(new CustomEvent('za-warudo-scene', {
                detail: {seconds: 2.5, toast: data.toast},
            }));
            await new Promise((resolve) => setTimeout(resolve, 2500));
        } catch (e) {
            // Показа не будет – сдаём сразу.
        }
    }
    return data;
}
