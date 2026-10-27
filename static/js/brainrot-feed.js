// Пасхалка «Чемпион по пролистыванию» (brainrot): лента роликов рядом с задачами
// (templates/quizzes/_brainrot_feed.html) и секрет, который её открывает
// (_easter_hunt.html). Грузится в pre_alpine_js: Alpine из CDN стартует сразу
// после своего тега, и компонент из extra_js не успевает.
//
// Показывать ли ленту, решает сервер (classwork.brainrot_visible). Страница
// сообщает перемены событием на window: `brainrot` с detail true/false –
// так опрос самостоятельной гасит ленту по запрету учителя, а найденная
// пасхалка включает её без перезагрузки.

function brainrotFeed(on) {
    const el = document.getElementById('brainrot-videos');
    const videos = (el ? JSON.parse(el.textContent) : []).sort(() => Math.random() - 0.5);
    return {
        // Порядок свой у каждого ученика: соседи по парте листают разное.
        videos,
        rotOn: on,
        // Крестик прячет ленту на время, выключить насовсем – в профиле.
        rotHidden: (() => { try { return localStorage.getItem('classwork-brainrot-hidden') === '1'; } catch (e) { return false; } })(),
        // Старт со случайного ролика: перемешивание через sort на коротком
        // списке почти не трогает первый элемент, и лента начиналась с одного.
        rotIndex: Math.floor(Math.random() * videos.length),
        rotDir: 1,
        rotPaused: false,
        _rotY: null,
        _rotAt: 0,

        rotGo(dir) {
            const n = this.videos.length;
            this.rotDir = dir;
            this.rotIndex = (this.rotIndex + dir + n) % n;
            this.rotPaused = false;
        },
        // Тачпад шлёт десятки событий на один жест – листаем не чаще раза в 0,6 с.
        rotWheel(e) {
            if (Math.abs(e.deltaY) < 4 || Date.now() - this._rotAt < 600) return;
            this._rotAt = Date.now();
            this.rotGo(e.deltaY > 0 ? 1 : -1);
        },
        rotDown(e) {
            this._rotY = e.clientY;
            e.currentTarget.setPointerCapture(e.pointerId);
        },
        // Потянул вверх – следующий ролик, как в ленте; короткий щелчок – пауза.
        rotUp(e) {
            if (this._rotY === null) return;
            const dy = e.clientY - this._rotY;
            this._rotY = null;
            if (Math.abs(dy) > 40) { this.rotGo(dy < 0 ? 1 : -1); return; }
            const video = e.currentTarget.querySelector('video');
            if (!video) return;
            if (video.paused) { video.play(); this.rotPaused = false; }
            else { video.pause(); this.rotPaused = true; }
        },
        rotClose() {
            this.rotHidden = true;
            try { localStorage.setItem('classwork-brainrot-hidden', '1'); } catch (e) {}
        },
        rotOpen() {
            this.rotHidden = false;
            try { localStorage.removeItem('classwork-brainrot-hidden'); } catch (e) {}
        },
    };
}

// Секрет: 10 переключений задач за 15 секунд. Страница шлёт `task-switch`
// из своего goTo; сервер открывает пасхалку один раз.
const HUNT_SWITCHES = 10;
const HUNT_WINDOW_MS = 15000;

function easterHunt(url, csrf) {
    return {
        _hits: [],
        _sent: false,
        toast: '',
        toastImage: '',

        tick() {
            if (this._sent) return;
            const now = Date.now();
            this._hits = this._hits.filter(t => now - t < HUNT_WINDOW_MS);
            this._hits.push(now);
            if (this._hits.length >= HUNT_SWITCHES) this._found();
        },

        async _found() {
            this._sent = true;
            try {
                const resp = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': csrf } });
                const data = await resp.json();
                if (!data.new) return;
                window.dispatchEvent(new CustomEvent('brainrot', { detail: true }));
                this.toastImage = data.image;
                this.toast = data.title;
                setTimeout(() => { this.toast = ''; }, 7000);
            } catch (e) {
                this._sent = false;  // сеть вернётся – следующая серия переключений попробует снова
            }
        },
    };
}
