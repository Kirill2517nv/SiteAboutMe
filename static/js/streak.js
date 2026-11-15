// Пасхалка «Серия» (streak): огонь по краям экрана за задачи, решённые
// подряд с первой попытки. Партиал – templates/quizzes/_streak.html.
// Грузится в pre_alpine_js рядом с brainrot-feed.js: Alpine стартует сразу
// после своего тега, и компонент из extra_js не успевает.
//
// Страницы шлют событие окна `task-verdict` с detail {id, correct, firstTry}:
// ege_practice.html – из check/giveUp, quiz_detail.html – из checkAnswer и
// handleCodeStatus. Счётчик живёт только в памяти страницы: перезагрузка
// начинает серию заново.

// Ступени серии. at – с какого счёта ступень включается, h – высота вспышки
// в % высоты окна, pal – палитра пламени, sparks – сколько искр в секунду
// сверх обычного. Уровень – наибольшая ступень <= счёта (7 -> «Неудержимый!»,
// 9 -> «Бог задачника!»). Звука нет: тренировку решает весь класс сразу.
const STREAK_LEVELS = [
    { at: 2, label: 'Две подряд!', h: 16, pal: 'amber', sparks: 26 },
    { at: 3, label: 'Три подряд!', h: 24, pal: 'amber', sparks: 10 },
    { at: 4, label: 'Ультра!', h: 36, pal: 'orange', sparks: 14 },
    { at: 5, label: 'Буйство!', h: 54, pal: 'orange', sparks: 20 },
    { at: 6, label: 'Неудержимый!', h: 88, pal: 'red', sparks: 26 },
    { at: 8, label: 'Бог задачника!', h: 94, pal: 'blue', sparks: 34 },
];

const STREAK_FLASH_MS = 2600;   // вспышка до высоты ступени
const STREAK_PHRASE_MS = 1700;  // крупная фраза по центру
const STREAK_DIE_MS = 1400;     // дым при сбросе
const STREAK_IDLE_H = 7;        // осевшее тлеющее пламя, % высоты окна
const STREAK_HUNT_AT = 3;       // на третьей задаче подряд серия находится

function streakLevel(count) {
    let found = null;
    for (const level of STREAK_LEVELS) {
        if (count >= level.at) found = level;
    }
    return found;
}

// Цвет частицы по возрасту: молодая (внизу) – раскалённое ядро, старая –
// тёмный кончик языка. Четыре опорных цвета, между ними – линейно.
const STREAK_PALETTES = {
    amber:  [[255, 248, 220], [255, 204, 84], [246, 120, 28], [120, 32, 8]],
    orange: [[255, 236, 196], [255, 160, 48], [236, 72, 16], [96, 16, 4]],
    red:    [[255, 222, 204], [255, 92, 44], [196, 20, 12], [64, 0, 4]],
    blue:   [[236, 246, 255], [128, 198, 255], [44, 98, 236], [20, 16, 84]],
    smoke:  [[150, 146, 142], [126, 122, 120], [100, 98, 96], [70, 68, 66]],
};
const SPRITE_STEPS = 16;
const SPRITE_PX = 64;

function streakColor(pal, t) {
    const stops = STREAK_PALETTES[pal];
    const x = Math.min(0.999, Math.max(0, t)) * (stops.length - 1);
    const i = Math.floor(x), f = x - i;
    return stops[i].map((c, k) => Math.round(c + (stops[i + 1][k] - c) * f));
}

// Движок пламени: две узкие канвы у краёв окна, на каждой – свои частицы
// (не зеркальная копия: одинаковые языки слева и справа выглядят нарисованными).
// Частица – мягкое пятно, сложение цветов ('lighter') само даёт белое ядро там,
// где пятна гуще. Пятна заранее нарисованы на маленьких канвах по палитре и
// возрасту: градиент на каждую частицу в каждом кадре – это сотни градиентов.
// Живёт в замыкании, а не в состоянии Alpine: канва внутри Proxy – та же
// ловушка, что описана в present-mode.js.
function streakFire() {
    const sides = [];
    const sprites = {};
    let W = 0, H = 0, dpr = 1, raf = 0, last = 0;
    let cur = 0, target = 0, pal = 'amber', sparkRate = 0;
    let dying = false, flashTimer = null, dieTimer = null;

    function sprite(name, k) {
        const key = name + k;
        if (sprites[key]) return sprites[key];
        const c = document.createElement('canvas');
        c.width = c.height = SPRITE_PX;
        const g = c.getContext('2d');
        const [r, gr, b] = streakColor(name, k / (SPRITE_STEPS - 1));
        const half = SPRITE_PX / 2;
        const grad = g.createRadialGradient(half, half, 0, half, half, half);
        grad.addColorStop(0, `rgba(${r},${gr},${b},1)`);
        grad.addColorStop(0.35, `rgba(${r},${gr},${b},0.5)`);
        grad.addColorStop(1, `rgba(${r},${gr},${b},0)`);
        g.fillStyle = grad;
        g.fillRect(0, 0, SPRITE_PX, SPRITE_PX);
        return (sprites[key] = c);
    }

    function resize() {
        dpr = Math.min(window.devicePixelRatio || 1, 1.5);
        for (const s of sides) {
            W = s.cv.clientWidth;
            H = s.cv.clientHeight;
            s.cv.width = Math.round(W * dpr);
            s.cv.height = Math.round(H * dpr);
        }
    }

    // x считается от внешнего края окна: 0 – самый край, W – внутрь страницы.
    function spawnFlame(s) {
        const life = 0.75 + Math.random() * 0.8;
        const reach = (cur / 100) * H;
        s.parts.push({
            x: Math.pow(Math.random(), 1.7) * W * 0.9,
            y: H + 8,
            vx: (Math.random() - 0.35) * W * 0.35,
            vy: -reach * (0.55 + Math.random() * 0.5) / life,
            age: 0, life,
            size: W * (0.5 + Math.random() * 0.55) * (0.75 + cur / 220),
            seed: Math.random() * 6.28,
            kind: 'flame',
        });
    }

    function spawnSpark(s) {
        const life = 0.9 + Math.random() * 1.1;
        const reach = Math.max(cur, 20) / 100 * H;
        s.parts.push({
            x: Math.random() * W * 0.7,
            y: H - Math.random() * reach * 0.4,
            vx: (Math.random() - 0.3) * 90,
            vy: -(reach * 0.7 + 120 + Math.random() * 160) / life,
            age: 0, life,
            size: 1.4 + Math.random() * 2.2,
            seed: Math.random() * 6.28,
            kind: 'spark',
        });
    }

    function spawnSmoke(s) {
        const reach = Math.max(cur, 10) / 100 * H;
        s.parts.push({
            x: Math.random() * W * 0.8,
            y: H - Math.random() * reach,
            vx: (Math.random() - 0.2) * 30,
            vy: -(40 + Math.random() * 70),
            age: 0, life: 1.1 + Math.random() * 0.6,
            size: W * (0.6 + Math.random() * 0.6),
            seed: Math.random() * 6.28,
            kind: 'smoke',
        });
    }

    function frame(now) {
        const dt = Math.min(0.05, last ? (now - last) / 1000 : 0.016);
        last = now;
        cur += (target - cur) * Math.min(1, dt * 3.5);
        const t = now / 1000;
        let alive = 0;

        for (const s of sides) {
            if (!dying && cur > 0.4) {
                s.acc += (12 + cur * 2.6) * dt;
                s.sparkAcc += sparkRate * dt * Math.min(1, cur / 10);
            }
            while (s.acc >= 1) { spawnFlame(s); s.acc -= 1; }
            while (s.sparkAcc >= 1) { spawnSpark(s); s.sparkAcc -= 1; }

            const ctx = s.ctx;
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, s.cv.width, s.cv.height);
            // Правая канва рисуется зеркально: координаты частиц – от края окна.
            ctx.setTransform(s.flip ? -dpr : dpr, 0, 0, dpr, s.flip ? s.cv.width : 0, 0);

            // Подсветка у основания – угли, на которых стоит пламя.
            if (cur > 0.4 && !dying) {
                const [r, g, b] = streakColor(pal, 0.25);
                const glow = ctx.createRadialGradient(0, H, 0, 0, H, W * 1.6);
                glow.addColorStop(0, `rgba(${r},${g},${b},${0.45 * Math.min(1, cur / 25)})`);
                glow.addColorStop(1, `rgba(${r},${g},${b},0)`);
                ctx.globalCompositeOperation = 'lighter';
                ctx.globalAlpha = 1;
                ctx.fillStyle = glow;
                ctx.fillRect(0, H - W * 1.6, W * 1.6, W * 1.6);
            }

            const keep = [];
            for (const p of s.parts) {
                p.age += dt / p.life;
                if (p.age >= 1) continue;
                keep.push(p);
                if (p.kind === 'flame') {
                    // Языки колышутся и чуть тянутся внутрь страницы.
                    p.vx += (Math.sin(t * 5 + p.seed) * W * 1.4 + W * 0.25) * dt;
                    p.vy -= H * 0.08 * dt;
                } else if (p.kind === 'spark') {
                    p.vx += Math.sin(t * 9 + p.seed) * 160 * dt;
                } else {
                    p.vx += Math.sin(t * 2 + p.seed) * 20 * dt;
                    p.size += W * 0.6 * dt;
                }
                p.x += p.vx * dt;
                p.y += p.vy * dt;

                let size, alpha, img;
                if (p.kind === 'flame') {
                    size = p.size * (1 - 0.7 * p.age);
                    alpha = (p.age < 0.12 ? p.age / 0.12 : Math.pow(1 - p.age, 1.2)) * 0.6;
                    img = sprite(dying ? 'smoke' : pal, Math.min(SPRITE_STEPS - 1, (p.age * SPRITE_STEPS) | 0));
                    ctx.globalCompositeOperation = dying ? 'source-over' : 'lighter';
                } else if (p.kind === 'spark') {
                    size = p.size * 5;
                    alpha = Math.pow(1 - p.age, 0.8) * (0.6 + 0.4 * Math.sin(t * 30 + p.seed));
                    img = sprite(pal, 1);
                    ctx.globalCompositeOperation = 'lighter';
                } else {
                    size = p.size;
                    alpha = Math.sin(p.age * Math.PI) * 0.28;
                    img = sprite('smoke', (p.age * 10) | 0);
                    ctx.globalCompositeOperation = 'source-over';
                }
                ctx.globalAlpha = Math.max(0, alpha);
                ctx.drawImage(img, p.x - size / 2, p.y - size / 2, size, size);
            }
            s.parts = keep;
            alive += keep.length;
        }

        if (alive === 0 && target === 0 && cur < 0.5) {
            raf = 0;
            last = 0;
            for (const s of sides) {
                s.ctx.setTransform(1, 0, 0, 1, 0, 0);
                s.ctx.clearRect(0, 0, s.cv.width, s.cv.height);
            }
            return;
        }
        raf = requestAnimationFrame(frame);
    }

    function run() {
        if (!raf) raf = requestAnimationFrame(frame);
    }

    return {
        attach(left, right) {
            for (const [cv, flip] of [[left, false], [right, true]]) {
                sides.push({ cv, flip, ctx: cv.getContext('2d'), parts: [], acc: 0, sparkAcc: 0 });
            }
            resize();
            window.addEventListener('resize', resize);
        },

        flash(level) {
            clearTimeout(flashTimer);
            clearTimeout(dieTimer);
            dying = false;
            if (!sides.length) return;
            if (!W) resize();
            pal = level.pal;
            target = level.h;
            sparkRate = 4 + level.sparks;
            // Вспышка: сноп искр сразу, не дожидаясь, пока пламя поднимется.
            for (const s of sides) for (let i = 0; i < level.sparks; i++) spawnSpark(s);
            flashTimer = setTimeout(() => { target = STREAK_IDLE_H; sparkRate = 3; }, STREAK_FLASH_MS);
            run();
        },

        die() {
            clearTimeout(flashTimer);
            clearTimeout(dieTimer);
            if (!sides.length || cur < 0.5) { target = 0; return; }
            dying = true;
            for (const s of sides) for (let i = 0; i < 10; i++) spawnSmoke(s);
            target = 0;
            dieTimer = setTimeout(() => { dying = false; }, STREAK_DIE_MS);
            run();
        },
    };
}

function streakFx(on, hunt, url, csrf) {
    const fire = streakFire();
    return {
        on,
        hunt,
        count: 0,
        level: 0,      // at текущей ступени – для цвета фразы и рамки
        label: '',
        phrase: false,
        toast: '',
        toastImage: '',
        toastText: '',
        _counted: new Set(),
        _sent: false,
        _phraseTimer: null,

        init() {
            fire.attach(this.$refs.fireLeft, this.$refs.fireRight);
        },

        verdict(v) {
            if (!v || this._counted.has(v.id)) return;  // одна задача – один раз
            if (v.correct && v.firstTry) {
                this._counted.add(v.id);
                this.count += 1;
                this._hunt();
                if (this.on) this._burn();
            } else if (!v.correct) {
                this.count = 0;
                if (this.on) this._reset();
            }
        },

        // Пока пасхалка не найдена, эффектов нет – работает только охота.
        async _hunt() {
            if (!this.hunt || this._sent || this.count < STREAK_HUNT_AT) return;
            this._sent = true;
            try {
                const resp = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': csrf } });
                const data = await resp.json();
                this.hunt = false;
                if (!data.new) return;
                this.on = true;  // эффекты включаются сразу на этой странице
                this.toastImage = data.image;
                this.toastText = data.toast;
                this.toast = data.title;
                this._burn();
                setTimeout(() => { this.toast = ''; }, 7000);
            } catch (e) {
                this._sent = false;  // сеть вернётся – следующий «+1» попробует снова
            }
        },

        _burn() {
            const level = streakLevel(this.count);
            if (!level) return;  // на первой задаче огня нет
            this.level = level.at;
            this.label = level.label;
            // Сначала убрать, потом показать: иначе фраза, уже стоящая на
            // экране, не проиграет анимацию появления заново.
            this.phrase = false;
            this.$nextTick(() => { this.phrase = true; });
            clearTimeout(this._phraseTimer);
            this._phraseTimer = setTimeout(() => { this.phrase = false; }, STREAK_PHRASE_MS);
            // prefers-reduced-motion: без пламени – только фраза и счётчик.
            if (!this._reduced()) fire.flash(level);
        },

        _reset() {
            clearTimeout(this._phraseTimer);
            this.phrase = false;
            fire.die();
        },

        _reduced() {
            return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        },


        // Панель отладки суперпользователя: ступень по кнопке, без решения задач.
        debugSet(n) {
            this.hunt = false;
            this.on = true;
            this.count = n;
            this._burn();
        },
        debugFail() {
            this.on = true;
            this.count = 0;
            this._reset();
        },
    };
}
