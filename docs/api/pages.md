# Pages API

Приложение `pages` обслуживает главную и about-страницу. Контент-блоки управляются через Django Admin.

---

## Endpoints

### GET `/` — Главная страница

**View:** `home_page_view`
**Auth:** Не требуется
**Template:** `home.html`

Парсит `CHANGELOG.md` и выводит историю изменений проекта. Структурирует версии, категории и элементы для шаблона.

---

### GET `/about/` — О проекте

**View:** `about_page_view`
**Auth:** Не требуется
**Template:** `about.html`

Загружает `ContentBlock` объекты с `page='about'` и отображает их с настроенной стилизацией (шрифты, цвета, layout).

**Контекст:**

| Переменная | Описание |
|------------|----------|
| `blocks` | QuerySet ContentBlock |
| `page_type` | `'about'` |
