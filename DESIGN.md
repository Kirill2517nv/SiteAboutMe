# Дизайн-система kirill-lab.ru

## Содержание
1. [Основы](#основы)
2. [Цвета](#цвета)
3. [Типографика](#типографика)
4. [Компоненты](#компоненты)
5. [Лейауты](#лейауты)
6. [Иконки](#иконки)
7. [Анимации](#анимации)

---

## Основы

### Технологии
- **Tailwind CSS** v3.x (CDN, `cdn.tailwindcss.com`)
- **Alpine.js** v3.14.3 (интерактивность, `x-data`, `x-show`, `x-transition`)
- **htmx** v1.9.10 (частичные обновления)
- **AOS** v2.3.1 (Animate on Scroll)
- **Swiper** v11 (слайдеры)
- **PhotoSwipe** v5 (лайтбокс изображений)
- **Highlight.js** v11.9.0 (подсветка кода, тема `atom-one-dark`)
- **CodeMirror** v5.65.18 (редактор кода, тема `material-darker`)

### Tailwind Config (расширения)
```js
tailwind.config = {
    theme: {
        extend: {
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
            },
            colors: {
                brand: {
                    50:  '#eff6ff',
                    100: '#dbeafe',
                    500: '#3b82f6',
                    600: '#2563eb',
                    700: '#1d4ed8',
                    900: '#1e3a8a',
                }
            }
        }
    }
}
```

### Принципы
1. **Mobile-first** — адаптивность через `sm:`, `md:`, `lg:` брейкпоинты
2. **Контент из БД** — стили (шрифты, цвета, фон) задаются через модели ContentBlock/LessonBlock
3. **Два режима UI** — публичный просмотр + inline-редактирование для staff
4. **Минимум кастомного CSS** — утилити Tailwind, отдельные CSS только для редактора

---

## Цвета

### Brand (кастомная палитра)
| Название | Tailwind | HEX | Использование |
|----------|----------|-----|---------------|
| Brand 50 | `brand-50` | `#eff6ff` | — |
| Brand 100 | `brand-100` | `#dbeafe` | Фон иконок, badge |
| Brand 500 | `brand-500` | `#3b82f6` | Focus ring |
| Brand 600 | `brand-600` | `#2563eb` | Основные кнопки, логотип, ссылки |
| Brand 700 | `brand-700` | `#1d4ed8` | Hover кнопок |
| Brand 900 | `brand-900` | `#1e3a8a` | — |

### Neutral
| Название | Tailwind | HEX | Использование |
|----------|----------|-----|---------------|
| Background | `gray-50` | `#f9fafb` | Фон `<body>`, sidebar header |
| Card | `white` | `#ffffff` | Карточки, навбар, футер |
| Border | `gray-100` | `#f3f4f6` | Границы карточек, разделители |
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
| Info | `blue-50`/`blue-500` | Информация, подсказки |
| Purple | `purple-600`/`purple-100` | Проверочные работы (отличие от учебных) |
| Indigo | `indigo-600`/`indigo-100` | Группы в статистике |

### Градиенты (используются в result-блоках)
```html
<!-- Успех -->
bg-gradient-to-r from-green-50 to-emerald-50

<!-- Предупреждение -->
bg-gradient-to-r from-amber-50 to-orange-50
```

---

## Типографика

### Шрифт
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```
Fallback: `system-ui, sans-serif`

### Масштаб
| Элемент | Классы | Где используется |
|---------|--------|------------------|
| Page Title | `text-4xl font-bold text-gray-900` | h1 на главной, quiz_list |
| Section Title | `text-3xl font-bold text-gray-900` | h1 на внутренних страницах |
| Card Title | `text-xl font-semibold text-gray-900` | Заголовки карточек, блоков |
| Section Header | `text-2xl font-bold text-gray-900` | "Учебные задачи", "Проверочные работы" |
| Subtitle | `text-lg text-gray-600` | Описание под заголовком |
| Body | `text-base text-gray-700` | Контент, prose-блоки |
| Small | `text-sm text-gray-500` | Мета-информация, даты |
| Caption | `text-xs text-gray-400` | Метки sidebar, uppercase tracking |
| Badge | `text-xs font-medium` | Статусы, счетчики |

### Специальные стили текста
```html
<!-- Mono (код, ответы) -->
font-mono text-sm

<!-- Uppercase label -->
text-xs font-semibold text-gray-400 uppercase tracking-wider
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

<!-- Purple (проверочные работы) -->
<button class="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg
               hover:bg-purple-700 transition-colors">
    Начать
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
<!-- Стандартная карточка (quiz_list, lesson_list) -->
<div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden
            hover:shadow-md transition-all duration-300">
    <div class="p-5">
        <!-- content -->
    </div>
</div>

<!-- Карточка Главной (home) — с hover-эффектом на изображение -->
<article class="group relative rounded-xl shadow-md hover:shadow-xl
                transition-all duration-300 overflow-hidden bg-white">
    <img class="w-full transition-transform duration-500 group-hover:scale-105" ...>
    <div class="p-5">
        <h3 class="text-xl font-bold text-gray-900 mb-2
                   group-hover:text-blue-600 transition-colors">
            Заголовок
        </h3>
        <p class="text-base text-gray-600 line-clamp-3">Текст</p>
    </div>
</article>

<!-- Карточка профиля — акцентированная -->
<div class="bg-white rounded-2xl shadow-lg p-6">
    <!-- content -->
</div>

<!-- Карточка авторизации — максимальный акцент -->
<div class="bg-white rounded-2xl shadow-xl p-8">
    <!-- content -->
</div>
```

### Иерархия теней карточек
| Контекст | Shadow | Rounded |
|----------|--------|---------|
| Обычная карточка | `shadow-sm` | `rounded-xl` |
| Hover карточки | `shadow-md` | `rounded-xl` |
| Home card | `shadow-md` → hover `shadow-xl` | `rounded-xl` |
| Профиль | `shadow-lg` | `rounded-2xl` |
| Авторизация | `shadow-xl` | `rounded-2xl` |
| Floating toolbar | `shadow-lg` (CSS: `0 4px 20px`) | `rounded-xl` |

### Badges / Status

```html
<!-- Status badge (универсальный) -->
<span class="px-2.5 py-1 text-xs font-medium rounded-full bg-green-100 text-green-700">
    Пройдено
</span>

<!-- Solved badge -->
<span class="inline-flex items-center gap-1 px-2.5 py-1 bg-green-100
             text-green-600 rounded-full text-xs font-semibold">
    Решено
</span>

<!-- Count badge -->
<span class="inline-flex items-center px-2.5 py-0.5 rounded-full
             text-xs font-medium bg-gray-100 text-gray-700">
    3
</span>
```

### Цветовая схема badges
| Состояние | BG | Text |
|-----------|-----|------|
| Пройдено / Успех | `bg-green-100` | `text-green-700` |
| Доступно (учебн.) | `bg-blue-100` | `text-blue-700` |
| Доступно (провер.) | `bg-purple-100` | `text-purple-700` |
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
<div class="w-full bg-gray-200 rounded-full h-3">
    <div class="h-3 rounded-full transition-all duration-500
                bg-green-500"  <!-- или bg-yellow-500, bg-red-500 -->
         style="width: 75%">
    </div>
</div>
```

Пороги: `>= 70%` — green, `>= 50%` — yellow, `< 50%` — red.

### Section Header (с иконкой)

```html
<div class="flex items-center mb-6">
    <div class="flex-shrink-0 w-10 h-10 bg-blue-100 rounded-lg
                flex items-center justify-center mr-4">
        <svg class="w-5 h-5 text-blue-600">...</svg>
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
<!-- Широкий (списки, статистика) — max-w-7xl -->
<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

<!-- Узкий (детали урока, результаты) — max-w-4xl -->
<div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

<!-- Центрированный (авторизация) — max-w-md -->
<div class="min-h-[60vh] flex items-center justify-center px-4 py-12">
    <div class="w-full max-w-md">
```

### Page Header (общий паттерн)
```html
<!-- Центрированный (главная, списки) -->
<div class="text-center mb-12">
    <h1 class="text-4xl font-bold text-gray-900 mb-4">Заголовок</h1>
    <p class="text-lg text-gray-600 max-w-2xl mx-auto">Описание</p>
</div>

<!-- Левосторонний (внутренние страницы) -->
<header class="mb-8">
    <h1 class="text-3xl font-bold text-gray-900 mb-2">Заголовок</h1>
    <p class="text-gray-600">Описание</p>
</header>
```

### Сетка карточек
```html
<!-- 3-колоночная сетка (quiz_list, home) -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

<!-- 2-колоночная сетка (профиль) -->
<div class="grid md:grid-cols-2 gap-6">
```

### Sidebar + Content (quiz_detail)
```html
<div class="flex gap-8">
    <!-- Sidebar: скрыт на мобилке, sticky -->
    <aside class="hidden lg:block w-64 flex-shrink-0">
        <div class="sticky top-[80px] max-h-[calc(100vh-100px)] overflow-y-auto">
            ...
        </div>
    </aside>

    <!-- Content: flex-1 -->
    <div class="flex-1 min-w-0">
        <div class="space-y-6">...</div>
    </div>
</div>
```

### Navbar
```html
<header class="bg-white shadow-sm sticky top-0 z-50">
    <nav class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
            <!-- logo + nav links (hidden md:flex) -->
            <!-- auth buttons -->
            <!-- mobile hamburger (md:hidden) -->
        </div>
    </nav>
    <!-- mobile dropdown (Alpine.js x-show) -->
</header>
```

### Footer
```html
<footer class="bg-white border-t mt-auto">
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
<!-- Круглый (профиль, quiz questions) -->
<div class="w-12 h-12 bg-brand-100 rounded-full flex items-center justify-center">
    <svg class="w-6 h-6 text-brand-600">...</svg>
</div>

<!-- Квадратный со скруглением (section headers) -->
<div class="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
    <svg class="w-5 h-5 text-blue-600">...</svg>
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
| `fade-right` | Навигация "Назад", sidebar |
| `data-aos-delay` | Каскад карточек: `{{ forloop.counter0 }}50` или `{{ forloop.counter0 }}00` |

### Tailwind Transitions
```html
transition-colors duration-200   /* Цвета (кнопки, ссылки) */
transition-all duration-300      /* Тени + цвета (карточки) */
transition-transform duration-500 /* Zoom изображений */
transition-shadow duration-200   /* Focus ring */
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
<!-- Карточка (home) — zoom image + shift link arrow -->
group-hover:scale-105          /* изображение */
group-hover:text-blue-600      /* заголовок */
group-hover:translate-x-1      /* стрелка "Подробнее" */

<!-- Кнопка "Назад" — shift arrow -->
group-hover:-translate-x-1     /* стрелка */

<!-- Карточка (list) — поднять тень -->
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

### Code Submission State Animations
```css
.code-question-card.checking {
    border-color: #fbbf24;
    box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.2);
}
.code-question-card.success {
    border-color: #22c55e;
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.2);
}
.code-question-card.failed {
    border-color: #ef4444;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.2);
}
```

---

## Кастомные CSS файлы

### `static/css/block-editor.css`
Стили для sidebar-редактора блоков (home page). Floating toolbar, sidebar panel 360px, backdrop, drag & drop.

### `static/css/content-editor-tailwind.css`
Стили для inline-редактирования контента. Использует `@apply` для Tailwind-совместимости. Включает: contenteditable стили, drag indicators, image context menu, resize handles, color picker.

---

## Breakpoints

| Breakpoint | Prefix | Где используется |
|------------|--------|------------------|
| < 768px | `md:hidden` | Mobile menu, однокол. сетка |
| >= 768px | `md:` | 2-колоночная сетка, горизонтальные лейауты блоков |
| >= 1024px | `lg:` | 3-колоночная сетка, sidebar quiz_detail |
| Контейнер | `sm:px-6 lg:px-8` | Padding контейнера |
