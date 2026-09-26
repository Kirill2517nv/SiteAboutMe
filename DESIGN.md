# Дизайн-система kirill-lab.ru

## Содержание
1. [Основы](#основы)
2. [Цвета](#цвета)
3. [Типографика](#типографика)
4. [Компоненты](#компоненты)
5. [Лейауты](#лейауты)
6. [Иконки](#иконки)
7. [Анимации](#анимации)
8. [Breakpoints](#breakpoints)

---

## Основы

### Технологии
- **Tailwind CSS** v3.4.19 – локальная сборка, CDN не используется. `static/css/tailwind.css` собирается из `static/css/tailwind.input.css` (`npm run tw:build`, `npm run tw:watch` – на лету); конфиг `tailwind.config.js` сканирует `templates/**/*.html` и `static/js/**/*.js`
- **Design tokens** – `static/css/design-tokens.css`: цвета, кегли, отступы, радиусы и тени CSS-переменными
- **Типографика статьи** – `static/css/textbook-article.css`: шкала кегля статьи и повторяющиеся блоки учебника
- **Alpine.js** v3.14.3 (интерактивность, `x-data`, `x-show`, `x-transition`)
- **htmx** v1.9.10 (частичные обновления)
- **AOS** v2.3.1 (Animate on Scroll)
- **Swiper** v11 (слайдеры)
- **PhotoSwipe** v5 (лайтбокс изображений)
- **Highlight.js** v11.9.0 (подсветка кода, тема `atom-one-dark`)
- **CodeMirror** v5.65.18 (редактор кода, тема `material-darker`)
- **MathJax** v3 (формулы, `tex-chtml`)

### Tailwind Config (`tailwind.config.js`)
```js
module.exports = {
  content: ['./templates/**/*.html', './static/js/**/*.js'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Полная шкала бренда: пропущенные ступени шаблоны уже использовали
        // (border-brand-300, text-brand-400), но Tailwind молча не выдаёт класс
        // для несуществующего оттенка – рамки и подписи оставались бесцветными.
        brand: {
          50:  '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        }
      }
    }
  },
  plugins: [],
}
```

**Сборка обязательна после новых классов.** Класс, которого не было ни в одном шаблоне, в `tailwind.css` отсутствует – браузер молча его игнорирует, и вёрстка выглядит неизменной.

### Принципы
1. **Mobile-first** – адаптивность через `sm:`, `md:`, `lg:` брейкпоинты
2. **Контент из БД** – стили (шрифты, цвета, фон) задаются через модели ContentBlock/LessonBlock
3. **Тёмная тема** – класс `dark` на `<html>`, выбор хранится в `localStorage`
4. **Минимум кастомного CSS** – утилити Tailwind, отдельные CSS-файлы только там, где утилитами не выразить (токены, типографика статьи)

---

## Цвета

Палитра продублирована CSS-переменными в `static/css/design-tokens.css` (`--color-brand-600`, `--color-text-muted` и т.д.) – типографика статьи и виджеты ходят через них, а не через утилиты Tailwind.

### Brand (кастомная палитра)
| Название | Tailwind | HEX | Использование |
|----------|----------|-----|---------------|
| Brand 50 | `brand-50` | `#eff6ff` | – |
| Brand 100 | `brand-100` | `#dbeafe` | Фон иконок, badge |
| Brand 200 | `brand-200` | `#bfdbfe` | – |
| Brand 300 | `brand-300` | `#93c5fd` | Рамки |
| Brand 400 | `brand-400` | `#60a5fa` | Шкала точности тренировок |
| Brand 500 | `brand-500` | `#3b82f6` | Focus ring |
| Brand 600 | `brand-600` | `#2563eb` | Основные кнопки, логотип, ссылки |
| Brand 700 | `brand-700` | `#1d4ed8` | Hover кнопок |
| Brand 800 | `brand-800` | `#1e40af` | – |
| Brand 900 | `brand-900` | `#1e3a8a` | – |

### Neutral
| Название | Tailwind | HEX | Использование |
|----------|----------|-----|---------------|
| Background | `gray-50` | `#f9fafb` | Фон `<body>`, sidebar header |
| Card | `white` | `#ffffff` | Карточки, навбар, футер |
| Border | `gray-100` | `#f3f4f6` | Границы карточек, разделители |
| Border Medium | `gray-200` | `#e5e7eb` | Рамки навбара и футера, разделители таблиц |
| Border Input | `gray-300` | `#d1d5db` | Границы инпутов |
| Text Muted | `gray-500` | `#6b7280` | Мета, подписи, второстепенный текст |
| Text Body | `gray-600` | `#4b5563` | Навигация, описания, ссылки |
| Text Default | `gray-700` | `#374151` | Основной текст контента |
| Heading | `gray-900` | `#111827` | Заголовки |

### Semantic
| Название | Tailwind | Использование |
|----------|----------|---------------|
| Success | `green-500`/`green-600` | Решено, правильно, скачать |
| Success BG | `green-50`/`green-100` | Фон успешных карточек |
| Warning | `amber-500`/`yellow-500` | Предупреждения, ожидание |
| Warning BG | `amber-50`/`yellow-50` | Фон предупреждений |
| Error | `red-500`/`red-600` | Ошибки, удаление, неверный ответ |
| Error BG | `red-50`/`red-100` | Фон ошибок |
| Info | `blue-50`/`blue-500` | Информация, подсказки; режим «Тренировка» |
| Purple | `purple-600`/`purple-100` | Разбор по памяти, частичный балл (задания 26–27) |
| Indigo | `indigo-600`/`indigo-100` | Группы в статистике |

### Градиенты (используются в result-блоках)
```html
<!-- Успех -->
bg-gradient-to-r from-green-50 to-emerald-50

<!-- Предупреждение -->
bg-gradient-to-r from-amber-50 to-orange-50
```

### Тёмная тема

Включается классом `dark` на `<html>` (`darkMode: 'class'` в конфиге). Скрипт в `<head>` ставит класс до отрисовки – по `localStorage.theme`, по умолчанию по системной настройке, – поэтому страница не мигает. Светлые утилиты перекрашиваются в `base.html` через `:where(.bg-white)`, `:where(.text-gray-700)` и т.п.: низкая специфичность нужна, чтобы `dark:*` и `hover:*` их перебивали. Типографика статьи переопределяет свою карту переменных в `textbook-article.css`.

Палитра – Slate: фон `#0f172a`, поверхность `#1e293b`, границы `#334155`, приглушённый текст `#94a3b8`, акцент ссылок `#22d3ee`.

---

## Типографика

### Шрифт
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```
Fallback: `system-ui, sans-serif`

### Масштаб

Шкала закрыта: девять ступеней, других размеров в проекте нет. Роль решает размер, а не страница – до шкалы один и тот же подзаголовок был 12px в отчёте о попытке и 18px на лендинге, а рядом жили произвольные значения между 9 и 17px.

| Роль | Класс | px |
|------|-------|-----|
| Ячейки таблиц, бейджи, счётчики, подписи под цифрой | `text-xs` | 12 |
| Мета, формы, вспомогательный текст, плотный интерфейс | `text-sm` | 14 |
| Основной текст, лид под заголовком страницы | `text-base` | 16 |
| Лид лендинга, текст статьи учебника | `text-lg` | 18 |
| Заголовок в компактной панели (шапка сессии, строка с аватаром), h3 | `text-xl` | 20 |
| h2 | `text-2xl` | 24 |
| h1 страницы | `text-2xl sm:text-3xl` | 24 → 30 |
| h1 лендинга (главные учебника, спецкурса, ЕГЭ, уроков, «Обо мне») | `text-4xl sm:text-5xl` | 36 → 48 |

Крупнее 48px – только display-цифры (балл прогноза, номера заданий на карте, игровое поле «Своей игры»): это графика, а не текст.

Статья учебника ходит через ту же шкалу своими переменными в `static/css/textbook-article.css`: `--fs-h1: 30px`, `--fs-h2: 24px`, `--fs-p: 18px`, `--fs-li: 18px`, `--fs-cap: 14px`, `--fs-table: 16px` (компактный вариант `.article-column--normal` – на ступень ниже). Для проектора у переменных есть rem-двойник: там масштаб задаётся корневым font-size, и px не вырос бы.

**Произвольный кегль мимо ступени роняет `FontScaleTest`** (`textbook/tests.py`): тест ищет в шаблонах `text-[Npx]` и `font-size:`. Ступень выбирается ближайшая, полпикселя «чтобы влезло» не добавляем. Исключения – четыре файла, где буквы работают как графика: `templates/home.html` (CSS-макеты сайта в миниатюре), `templates/games/svoya_igra/play.html` (кегль подобран под клетку поля), `templates/accounts/alumni.html` и `templates/about.html` (год выпуска, стрелки Swiper).

### Специальные стили текста
```html
<!-- Mono (код, ответы) -->
font-mono text-sm

<!-- Uppercase label (заголовок таблицы, метка отчёта) -->
text-xs font-semibold text-gray-600 uppercase tracking-wider
```

---

## Компоненты

### Кнопки

```html
<!-- Primary (brand) -->
<button class="px-4 py-2 bg-brand-600 text-white font-medium rounded-lg
               hover:bg-brand-700 focus:ring-2 focus:ring-brand-500
               focus:ring-offset-2 transition-colors">
    Действие
</button>

<!-- Primary Large -->
<button class="px-8 py-3 bg-brand-600 text-white font-medium rounded-lg
               hover:bg-brand-700 focus:ring-2 focus:ring-brand-500
               focus:ring-offset-2 transition-colors">
    Завершить тест
</button>

<!-- Secondary -->
<button class="px-4 py-2 bg-gray-100 text-gray-700 font-medium rounded-lg
               hover:bg-gray-200 transition-colors">
    Отмена
</button>

<!-- Success (проверка кода) -->
<button class="px-4 py-2 bg-green-600 text-white font-medium rounded-lg
               hover:bg-green-700 focus:ring-2 focus:ring-green-500
               focus:ring-offset-2 transition-colors">
    Проверить решение
</button>

<!-- Переключатель режима (разбор решения: «по скорости» / «по памяти»),
     активное состояние привязано к Alpine-состоянию -->
<button class="px-3 py-1.5 text-xs rounded-lg border transition-colors
               bg-purple-600 text-white border-purple-600">
    По памяти
</button>

<!-- Danger (logout, delete) -->
<button class="text-gray-500 hover:text-red-600 font-medium transition-colors">
    Выйти
</button>

<!-- Disabled -->
<button class="... disabled:opacity-50 disabled:cursor-not-allowed" disabled>
    Попытки исчерпаны
</button>
```

### Карточки

```html
<!-- Стандартная карточка (страницы со списками: уроки, задачи, попытки) -->
<div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden
            hover:shadow-md transition-all duration-300">
    <div class="p-5">
        <!-- content -->
    </div>
</div>

<!-- Карточка с обложкой (уроки, задачи спецкурса) – zoom изображения при наведении -->
<a href="..."
   class="group block bg-white rounded-xl shadow-sm hover:shadow-md border border-gray-100
          overflow-hidden transition-all duration-300">
    <div class="aspect-video overflow-hidden">
        <img class="w-full h-full object-cover transition-transform duration-500
                    group-hover:scale-105" ...>
    </div>
    <div class="p-5">
        <h3 class="text-base font-semibold text-gray-900
                   group-hover:text-brand-600 transition-colors">
            Заголовок
        </h3>
    </div>
</a>

<!-- Шапка профиля – акцентированная -->
<div class="bg-gradient-to-r from-brand-600 to-brand-700 rounded-2xl p-6 sm:p-8 text-white">
    <!-- content -->
</div>

<!-- Карточка авторизации – максимальный акцент -->
<div class="bg-white rounded-2xl shadow-xl p-8">
    <!-- content -->
</div>
```

### Иерархия теней карточек
| Контекст | Shadow | Rounded |
|----------|--------|---------|
| Обычная карточка | `shadow-sm` | `rounded-xl` |
| Hover карточки | `shadow-md` | `rounded-xl` |
| Блок-карточка «Обо мне» | `shadow-md` | `rounded-xl` |
| Модальное окно | `shadow-xl` | `rounded-xl` |
| Авторизация | `shadow-xl` | `rounded-2xl` |

### Badges / Status

```html
<!-- Status badge (универсальный) -->
<span class="px-2.5 py-1 text-xs font-medium rounded-full bg-green-100 text-green-700">
    Пройдено
</span>

<!-- Solved badge – свой CSS-класс, не утилиты (quiz_detail.html) -->
<span class="solved-badge ml-auto">Решено</span>

<!-- Count badge -->
<span class="inline-flex items-center px-2.5 py-0.5 rounded-full
             text-xs font-medium bg-gray-100 text-gray-700">
    3
</span>
```

`.solved-badge` объявлен в `quiz_detail.html`: `background: #dcfce7`, `color: #16a34a`, `border-radius: 9999px`, `font-size: 0.75rem`, `font-weight: 600`.

### Цветовая схема badges
| Состояние | BG | Text |
|-----------|-----|------|
| Пройдено / Успех | `bg-green-100` | `text-green-700` |
| Тренировка (режим сессии) | `bg-blue-100` | `text-blue-700` |
| Экзамен (режим сессии) | `bg-orange-100` | `text-orange-700` |
| Частичный балл (задания 26–27) | `bg-purple-100` | `text-purple-700` |
| Недоступно | `bg-gray-100` | `text-gray-500` |
| Ожидание | `bg-yellow-100` | `text-yellow-700` |

### Навигация "Назад"

```html
<nav class="mb-6">
    <a href="..." class="inline-flex items-center text-gray-500
                         hover:text-brand-600 transition-colors group">
        <svg class="w-5 h-5 mr-2 transition-transform group-hover:-translate-x-1"
             fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round"
                  stroke-width="2" d="M15 19l-7-7 7-7"/>
        </svg>
        Назад к списку
    </a>
</nav>
```

### Формы

```html
<!-- Input -->
<input type="text"
       class="w-full px-4 py-3 border border-gray-300 rounded-lg
              focus:ring-2 focus:ring-brand-500 focus:border-brand-500
              transition-colors"
       placeholder="Введите текст">

<!-- Label -->
<label class="block text-sm font-medium text-gray-700 mb-1">
    Название поля
</label>

<!-- Radio choice (quiz) -->
<label class="flex items-center p-3 border border-gray-200 rounded-lg
              cursor-pointer hover:bg-gray-50 hover:border-gray-300 transition-colors">
    <input type="radio" class="w-4 h-4 text-brand-600 border-gray-300
                                focus:ring-brand-500">
    <span class="ml-3 text-gray-700">Вариант ответа</span>
</label>
```

### Alerts / Banners

```html
<!-- Info banner -->
<div class="bg-blue-50 border-l-4 border-blue-500 rounded-r-lg p-4">
    <div class="flex items-start">
        <svg class="w-5 h-5 text-blue-500 mr-2 mt-0.5">...</svg>
        <p class="text-sm text-blue-800">Информация</p>
    </div>
</div>

<!-- Warning banner -->
<div class="px-5 py-4 bg-amber-50 border border-amber-200 rounded-xl
            flex items-center gap-3">
    <svg class="w-6 h-6 text-amber-500 flex-shrink-0">...</svg>
    <div>
        <p class="font-medium text-amber-800">Предупреждение</p>
        <p class="text-sm text-amber-600">Подробности</p>
    </div>
</div>

<!-- Error banner -->
<div class="p-4 bg-red-50 border border-red-200 rounded-lg">
    <div class="flex items-center">
        <svg class="w-5 h-5 text-red-500 mr-2">...</svg>
        <span class="text-red-700 text-sm">Ошибка</span>
    </div>
</div>

<!-- Error border-left -->
<div class="bg-red-50 border-l-4 border-red-500 rounded-r-lg p-4">
    <pre class="text-sm text-red-700 whitespace-pre-wrap font-mono">...</pre>
</div>
```

### Таблицы

```html
<div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
    <div class="overflow-x-auto">
        <table class="w-full">
            <thead>
                <tr class="bg-gray-50 border-b border-gray-100">
                    <th class="px-6 py-4 text-left text-xs font-semibold
                               text-gray-600 uppercase tracking-wider">
                        Заголовок
                    </th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
                <tr class="hover:bg-gray-50 transition-colors">
                    <td class="px-6 py-4">Значение</td>
                </tr>
            </tbody>
        </table>
    </div>
</div>
```

### Прогресс-бар

```html
<div class="h-2 rounded-full bg-gray-100 dark:bg-slate-700 overflow-hidden">
    <div class="h-full rounded-full bg-brand-400" style="width: 75%"></div>
</div>
```

Цветных порогов в проекте один: шкала точности по экзамену на карточке задания (`ege_task.html`) – `>= 75%` `bg-emerald-500`, `>= 50%` `bg-amber-500`, ниже `bg-red-500`. Остальные шкалы (точность тренировок, прогресс чтения, прогноз) – одноцветные, `bg-brand-400` или `bg-brand-600`.

### Section Header (с иконкой)

```html
<div class="flex items-center mb-6">
    <div class="flex-shrink-0 w-10 h-10 bg-brand-100 rounded-lg
                flex items-center justify-center mr-4">
        <svg class="w-5 h-5 text-brand-600">...</svg>
    </div>
    <h2 class="text-2xl font-bold text-gray-900">Учебные задачи</h2>
</div>
```

### Empty State

```html
<div class="bg-gray-50 rounded-xl p-8 text-center">
    <div class="text-gray-400 mb-2">
        <svg class="w-12 h-12 mx-auto">...</svg>
    </div>
    <p class="text-gray-500">Нет доступных задач</p>
</div>

<!-- Большой empty state -->
<div class="bg-gray-50 rounded-xl p-12 text-center">
    <svg class="w-16 h-16 mx-auto text-gray-300 mb-4">...</svg>
    <h3 class="text-xl font-semibold text-gray-700 mb-2">Нет данных</h3>
    <p class="text-gray-500">Описание</p>
</div>
```

---

## Лейауты

### Контейнер страницы
```html
<!-- Широкий (списки, статистика) – max-w-7xl -->
<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

<!-- Узкий (детали урока, результаты) – max-w-4xl -->
<div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

<!-- Центрированный (авторизация) – max-w-md -->
<div class="min-h-[60vh] flex items-center justify-center px-4 py-12">
    <div class="w-full max-w-md">
```

### Page Header (общий паттерн)
```html
<!-- Центрированный (лендинги: учебник, спецкурс, ЕГЭ, уроки) -->
<div class="text-center mb-12">
    <h1 class="text-4xl sm:text-5xl font-bold text-gray-900 mb-4">Заголовок</h1>
    <p class="text-lg text-gray-600 max-w-2xl mx-auto">Описание</p>
</div>

<!-- Левосторонний (внутренние страницы) -->
<header class="mb-8">
    <h1 class="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">Заголовок</h1>
    <p class="text-gray-600">Описание</p>
</header>
```

### Сетка карточек
```html
<!-- 3-колоночная сетка (списки уроков, задач спецкурса, тем игр) -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

<!-- Плитки профиля -->
<div class="grid md:grid-cols-3 gap-6">
```

### Sidebar + Content (статья учебника)
```html
<!-- Список уроков/статей слева: скрыт на мобилке, сворачивается кнопкой-«язычком» -->
<aside class="article-sidebar-col hidden md:block" :class="sidebarOpen ? '' : 'w-collapsed'">
    <div class="article-sidebar-inner">...</div>
</aside>

<!-- Колонка текста -->
<div class="article-column">...</div>
```

Ширина, sticky-поведение и сворачивание этого сайдбара заданы не утилитами, а классами `.article-sidebar-*` в `static/css/textbook-article.css`.

### Navbar
```html
<header class="bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-700
               sticky top-0 z-50">
    <nav class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
            <!-- logo + nav links (hidden md:flex) -->
            <!-- переключатель темы + auth buttons -->
            <!-- mobile hamburger (md:hidden) -->
        </div>
    </nav>
    <!-- mobile dropdown (Alpine.js x-show, @click.outside) -->
</header>
```

### Footer
```html
<footer class="bg-white dark:bg-slate-900 border-t border-gray-200 dark:border-slate-700 mt-auto">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <p class="text-center text-gray-500 text-sm">
            &copy; Автор. Год
        </p>
    </div>
</footer>
```

---

## Иконки

### Источник
Inline SVG (Heroicons Outline), `24x24` viewBox.

### Размеры
| Контекст | Класс |
|----------|-------|
| Кнопка / inline | `w-4 h-4` или `w-5 h-5` |
| Section icon | `w-5 h-5` (в контейнере `w-10 h-10`) |
| Header icon | `w-6 h-6` (в контейнере `w-12 h-12`) |
| Large icon | `w-8 h-8` (в контейнере `w-16 h-16`) |
| Empty state | `w-12 h-12` или `w-16 h-16` |

### Стиль
```html
<!-- Outline (стандартный) -->
<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="..."/>
</svg>

<!-- Filled (галочка в badge/sidebar) -->
<svg fill="currentColor" viewBox="0 0 20 20">
    <path fill-rule="evenodd" d="..." clip-rule="evenodd"/>
</svg>
```

### Контейнер иконки
```html
<!-- Круглый (профиль, вопросы теста) -->
<div class="w-12 h-12 bg-brand-100 rounded-full flex items-center justify-center">
    <svg class="w-6 h-6 text-brand-600">...</svg>
</div>

<!-- Квадратный со скруглением (заголовки секций) -->
<div class="w-10 h-10 bg-brand-100 rounded-lg flex items-center justify-center">
    <svg class="w-5 h-5 text-brand-600">...</svg>
</div>
```

---

## Анимации

### AOS (Animate on Scroll)
```js
AOS.init({
    duration: 600,
    easing: 'ease-out-cubic',
    once: true,
});
```

Используемые эффекты:
| Эффект | Где |
|--------|-----|
| `fade-up` | Карточки, секции, основной контент |
| `fade-down` | Заголовок страницы |
| `fade-right` | Навигация "Назад", заголовки разделов «Обо мне» |
| `data-aos-delay` | Каскад карточек: `{{ forloop.counter0 }}50` или `{{ forloop.counter0 }}00` |

### Tailwind Transitions
```html
transition-colors                 /* Цвета (кнопки, ссылки) – длительность по умолчанию, 150 мс */
transition-all duration-200       /* Нажатия, оверлеи */
transition-all duration-300       /* Тени + цвета (карточки) */
transition-transform duration-500 /* Zoom изображений */
```

### Alpine.js Transitions
```html
<!-- Mobile menu -->
x-transition:enter="transition ease-out duration-200"
x-transition:enter-start="opacity-0 -translate-y-1"
x-transition:enter-end="opacity-100 translate-y-0"
x-transition:leave="transition ease-in duration-150"
x-transition:leave-start="opacity-100 translate-y-0"
x-transition:leave-end="opacity-0 -translate-y-1"

<!-- Collapsible sections -->
x-transition   <!-- Alpine default -->
```

### Hover Effects
```html
<!-- Карточка с обложкой – zoom изображения, подсветка заголовка -->
group-hover:scale-105          /* изображение */
group-hover:text-brand-600     /* заголовок */
group-hover:translate-x-1      /* стрелка "Подробнее" */

<!-- Кнопка "Назад" – shift arrow -->
group-hover:-translate-x-1     /* стрелка */

<!-- Карточка (list) – поднять тень -->
hover:shadow-md                /* с shadow-sm */
```

### CSS Animations (quiz_detail)
```css
/* Пульсация (ожидание) */
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* Вращение (загрузка) */
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
```

### Состояния проверки ответа
```css
/* ege_detail.html, quiz_detail.html */
.code-status {
    padding: 0.5em 0.75em; border-radius: 8px; font-size: 0.875rem;
    margin-top: 0.5em; display: flex; align-items: center; gap: 0.5em;
}
.code-status.pending, .code-status.running { background: #fef3c7; color: #92400e; }
.code-status.success { background: #dcfce7; color: #166534; }
.code-status.failed, .code-status.error { background: #fee2e2; color: #991b1b; }
```

Блок показывается по Alpine-состоянию: `checkingAnswer` меняет подпись кнопки на «Проверяю...», `codeStatuses` держит статус асинхронной проверки (`pending` / `running` / `success` / `failed` / `error`) – он приходит по WebSocket из `static/js/quiz-async.js`. Неверный текстовый ответ дополнительно красит сам инпут: `border-red-400 bg-red-50 text-red-700`.

---

## Breakpoints

| Breakpoint | Prefix | Где используется |
|------------|--------|------------------|
| < 768px | `md:hidden` | Mobile menu, однокол. сетка |
| >= 768px | `md:` | 2-колоночная сетка, горизонтальные лейауты блоков |
| >= 1024px | `lg:` | 3-колоночная сетка, сайдбар статьи учебника |
| Контейнер | `sm:px-6 lg:px-8` | Padding контейнера |
