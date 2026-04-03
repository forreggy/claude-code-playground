# Инвентарный реестр проекта TaigaBot Lite

**Дата генерации:** 3 апреля 2026
**Проект:** TaigaBot Lite («Леший») — Telegram-бот мониторинга группового чата с AI-сводками, генерацией мемов и четырьмя интерфейсами взаимодействия.

---

## Оглавление

1. [Дерево файлов](#1-дерево-файлов)
2. [Модули Python](#2-модули-python)
3. [HTTP-эндпоинты](#3-http-эндпоинты)
4. [Telegram-хэндлеры](#4-telegram-хэндлеры)
5. [База данных](#5-база-данных)
6. [Переменные окружения](#6-переменные-окружения)
7. [Зависимости](#7-зависимости)
8. [HTML-шаблоны](#8-html-шаблоны)

---

## 1. Дерево файлов

```
claude-code-playground/
├── .env.example            — шаблон переменных окружения (без реальных ключей)
├── .gitignore              — исключения Git (.env, taigabot.db, venv/, __pycache__/)
├── CLAUDE.md               — инструкции для Claude Code Web (контекст агента)
├── LICENSE                 — лицензия проекта
├── README.md               — описание проекта для GitHub
├── auth.py                 — авторизация: Telegram Login (JWT), Mini App initData, middleware сессий
├── bot.py                  — точка входа: polling + APScheduler + aiohttp веб-сервер
├── chat.py                 — интерактивный чат с Лешим (Cerebras API + DuckDuckGo поиск)
├── config.py               — загрузка и валидация переменных окружения
├── database.py             — все SQL-запросы (CRUD), инициализация БД, миграции
├── dialog_handlers.py      — Telegram-хэндлеры ЛС: команды, кнопки, callback, catch-all
├── imagegen.py             — генерация мем-картинок через OpenAI + наложение подписи (Pillow)
├── ingest.py               — приём и сохранение сообщений из группового чата
├── llm.py                  — генерация сводок через OpenAI Responses API + парсинг ответа
├── requirements.txt        — зависимости с зафиксированными версиями
├── static/
│   └── style.css           — стили веб-дашборда
├── taigabot.service        — шаблон systemd unit-файла
├── templates/
│   ├── base.html           — базовый HTML-шаблон (Jinja2), навигация, тёмная тема
│   ├── dashboard.html      — пульт администратора (чат, статистика, редактор промптов)
│   ├── login.html          — страница авторизации через Telegram Login Widget
│   ├── miniapp.html        — Telegram Mini App (standalone, лента + чат + пульт)
│   └── summaries.html      — публичная лента сводок (extends base.html)
├── test_llm.py             — тестовый скрипт для LLM
├── test_worker.py          — тестовый скрипт для worker (ручной запуск сводки)
└── web_app.py              — aiohttp-приложение: маршруты дашборда, Mini App, API
```

26 файлов, 14 модулей Python, 5 HTML-шаблонов.

---

## 2. Модули Python

### auth.py — авторизация и управление сессиями

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `_validate_jwt` | да | `(id_token: str) -> dict[str, Any]` | Валидация JWT id_token от Telegram Login |
| `_validate_legacy_hash` | нет | `(data: dict[str, Any]) -> dict[str, Any]` | Валидация hash-based данных Telegram Login Widget |
| `auth_middleware` | да | `(request, handler) -> StreamResponse` | Middleware: загрузка данных пользователя из сессии в `request['user']` |
| `handle_login_page` | да | `(request) -> Response` | `GET /auth/login` — страница с кнопкой Telegram Login Widget |
| `handle_auth_callback` | да | `(request) -> Response` | `GET /auth/callback` — обработка redirect от Telegram |
| `handle_logout` | да | `(request) -> Response` | `POST /auth/logout` — очистка сессии |
| `validate_mini_app_init_data` | нет | `(init_data_raw: str, bot_token: str) -> dict \| None` | Валидация initData от Telegram Mini App (HMAC) |

### bot.py — точка входа

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `main` | да | `() -> None` | Инициализация бота, запуск web-сервера, scheduler и polling |

### chat.py — интерактивный чат с Лешим

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `get_chat_prompt` | да | `() -> str` | Чтение chat_system_prompt из settings, fallback на DEFAULT_CHAT_PROMPT |
| `execute_web_search` | нет | `(query: str, max_results: int = 5) -> str` | Поиск через DuckDuckGo, возвращает результаты как текст |
| `chat_with_leshy` | да | `(dialog_id: int, user_message: str) -> str` | Основная функция чата: контекст диалога → LLM → ответ |

### config.py — конфигурация

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `_require` | нет | `(name: str) -> str` | Получить обязательную переменную окружения или выбросить ValueError |
| `_parse_admin_ids` | нет | `() -> frozenset[int]` | Парсинг ADMIN_IDS из окружения |
| `_parse_dialog_allowed_ids` | нет | `() -> list[int]` | Парсинг DIALOG_ALLOWED_IDS из окружения |

### database.py — работа с БД

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `init_db` | да | `() -> None` | Создание таблиц, индексов, PRAGMA, миграции |
| `save_message` | да | `(user_id, username, text, timestamp) -> None` | Сохранить входящее сообщение |
| `get_messages_since` | да | `(since_ts: int) -> list[dict]` | Все сообщения с timestamp >= since_ts |
| `save_summary` | да | `(date, summary_text, created_at, image_path) -> None` | Сохранить сводку в архив |
| `get_summaries_for_feed` | да | `(limit, offset) -> list[dict]` | Сводки для веб-ленты (обратная хронология) |
| `get_all_summaries` | да | `() -> list[dict]` | Все сводки для Mini App |
| `delete_messages_older_than` | да | `(ts: int) -> None` | Удаление устаревших сообщений |
| `get_setting` | да | `(key: str) -> str \| None` | Получить значение настройки |
| `set_setting` | да | `(key, value, updated_at) -> None` | Установить настройку (INSERT OR REPLACE) |
| `delete_setting` | да | `(key: str) -> None` | Удалить настройку |
| `get_prompt_history` | да | `(limit, prompt_key) -> list[dict]` | История версий промпта |
| `save_prompt_history` | да | `(prompt_text, changed_at, changed_by, prompt_key) -> None` | Сохранить версию промпта |
| `create_dialog` | да | `(user_id: int) -> int` | Создать новый диалог, вернуть id |
| `get_dialogs` | да | `(user_id: int) -> list[dict]` | Список диалогов пользователя |
| `get_dialog` | да | `(dialog_id: int) -> dict \| None` | Метаданные одного диалога |
| `delete_dialog` | да | `(dialog_id: int) -> None` | Удалить диалог и все сообщения (CASCADE) |
| `delete_all_dialogs` | да | `(user_id: int) -> None` | Удалить все диалоги пользователя |
| `update_dialog_timestamp` | да | `(dialog_id: int) -> None` | Обновить updated_at на текущее время |
| `update_dialog_title` | да | `(dialog_id, title) -> None` | Установить заголовок диалога |
| `add_dialog_message` | да | `(dialog_id, role, content) -> int` | Добавить сообщение в диалог |
| `get_dialog_messages` | да | `(dialog_id, limit) -> list[dict]` | Сообщения диалога (с лимитом, для контекста LLM) |
| `get_all_dialog_messages` | да | `(dialog_id: int) -> list[dict]` | Все сообщения диалога (для экспорта) |
| `get_stats` | да | `() -> dict` | Статистика из всех таблиц |

### dialog_handlers.py — Telegram-хэндлеры в ЛС

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `_main_keyboard` | нет | `() -> ReplyKeyboardMarkup` | Постоянная клавиатура: Диалоги / Новый / Помощь |
| `_dialog_keyboard` | нет | `(dialog_id: int) -> InlineKeyboardMarkup` | Инлайн-кнопки диалога: Экспорт / Удалить |
| `_confirm_keyboard` | нет | `(dialog_id: int) -> InlineKeyboardMarkup` | Кнопки подтверждения удаления: Да / Отмена |
| `cmd_start` | да | `(message) -> None` | `/start` — приветствие + постоянная клавиатура |
| `cmd_new` | да | `(message) -> None` | `/new` — создать новый диалог |
| `cmd_dialogs` | да | `(message) -> None` | `/dialogs` — список диалогов |
| `cmd_export` | да | `(message) -> None` | `/export` — экспорт текущего диалога текстом |
| `cmd_delete` | да | `(message) -> None` | `/delete` — удалить текущий диалог |
| `cmd_deleteall` | да | `(message) -> None` | `/deleteall` — удалить все диалоги |
| `btn_new` | да | `(message) -> None` | Кнопка «Новый» |
| `btn_dialogs` | да | `(message) -> None` | Кнопка «Диалоги» |
| `btn_help` | да | `(message) -> None` | Кнопка «Помощь» |
| `cb_export` | да | `(callback) -> None` | Callback: экспорт диалога |
| `cb_delete` | да | `(callback) -> None` | Callback: запрос подтверждения удаления |
| `cb_delete_yes` | да | `(callback) -> None` | Callback: подтверждение удаления |
| `cb_delete_no` | да | `(callback) -> None` | Callback: отмена удаления |
| `handle_private_message` | да | `(message) -> None` | Catch-all: входящее ЛС → диалог → LLM → ответ |
| `typing_loop` | да | `() -> None` | Повтор send_chat_action typing каждые 4 секунды |

### imagegen.py — генерация мем-картинок

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `_overlay_caption` | нет | `(image_bytes: bytes, caption: str) -> BytesIO` | Наложить подпись на полупрозрачную плашку |
| `generate_meme_image` | да | `(prompt: str, caption: str) -> BytesIO \| None` | Сгенерировать картинку и наложить подпись |

### ingest.py — приём сообщений

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `handle_message` | да | `(message) -> None` | Принять текстовое сообщение из группы и сохранить в БД |

### llm.py — генерация сводок

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `get_current_prompt` | да | `() -> str` | Получить текущий системный промпт сводок |
| `generate_summary` | да | `(messages: list[dict]) -> str` | Генерация вечерней сводки через OpenAI Responses API |
| `parse_summary_response` | нет | `(text: str) -> dict` | Парсинг ответа LLM: извлечение image_prompt, image_caption, текста |

### web_app.py — веб-приложение (aiohttp)

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `_format_date` | нет | `(date_str: str) -> str` | YYYY-MM-DD → «24 марта 2026» |
| `create_web_app` | нет | `() -> Application` | Создание и настройка aiohttp-приложения |
| `handle_index` | да | `(request) -> dict` | `GET /` — публичная лента сводок |
| `_get_default_prompt` | нет | `(prompt_key: str) -> str` | Дефолтный промпт по ключу |
| `_get_changed_by` | нет | `(user: dict) -> str` | Строка changed_by из данных сессии |
| `handle_admin_stats` | да | `(request) -> Response` | `GET /admin/stats` — JSON статистика |
| `handle_admin_prompt` | да | `(request) -> Response` | `GET /admin/prompt` — текущий промпт + история |
| `handle_admin_prompt_save` | да | `(request) -> Response` | `POST /admin/prompt` — сохранить промпт |
| `handle_admin_prompt_reset` | да | `(request) -> Response` | `POST /admin/prompt/reset` — сброс к дефолту |
| `handle_admin_prompt_history` | да | `(request) -> Response` | `GET /admin/prompt/history` — история версий |
| `_require_own_dialog` | да | `(dialog_id, user_id) -> dict` | Проверка владения диалогом |
| `handle_chat_dialogs_list` | да | `(request) -> Response` | `GET /admin/chat/dialogs` — список диалогов |
| `handle_chat_dialog_create` | да | `(request) -> Response` | `POST /admin/chat/dialogs` — создать диалог |
| `handle_chat_messages_list` | да | `(request) -> Response` | `GET /admin/chat/dialogs/{id}/messages` — история |
| `handle_chat_message_send` | да | `(request) -> Response` | `POST /admin/chat/dialogs/{id}/messages` — отправить |
| `_get_miniapp_user` | да | `(request) -> dict \| None` | Получить miniapp_user из сессии |
| `_require_miniapp_dialog_user` | да | `(request) -> tuple` | Проверка авторизации + право на диалог (Mini App) |
| `_require_miniapp_admin` | да | `(request) -> tuple` | Проверка авторизации + права админа (Mini App) |
| `miniapp_index` | да | `(request) -> Response` | `GET /miniapp/` — шелл Mini App |
| `miniapp_auth` | да | `(request) -> Response` | `POST /miniapp/auth` — авторизация через initData |
| `miniapp_feed` | да | `(request) -> Response` | `GET /miniapp/feed` — лента сводок JSON |
| `miniapp_chat_dialogs` | да | `(request) -> Response` | `GET /miniapp/chat/dialogs` — список диалогов |
| `miniapp_chat_create_dialog` | да | `(request) -> Response` | `POST /miniapp/chat/dialogs` — создать диалог |
| `miniapp_chat_messages` | да | `(request) -> Response` | `GET /miniapp/chat/dialogs/{id}/messages` — история |
| `miniapp_chat_send` | да | `(request) -> Response` | `POST /miniapp/chat/dialogs/{id}/messages` — отправить |
| `miniapp_admin_stats` | да | `(request) -> Response` | `GET /miniapp/admin/stats` — статистика |
| `miniapp_admin_prompt_get` | да | `(request) -> Response` | `GET /miniapp/admin/prompt` — оба промпта |
| `miniapp_admin_prompt_save` | да | `(request) -> Response` | `POST /miniapp/admin/prompt` — сохранить промпт |
| `miniapp_admin_prompt_reset` | да | `(request) -> Response` | `POST /miniapp/admin/prompt/reset` — сброс |
| `miniapp_admin_prompt_history` | да | `(request) -> Response` | `GET /miniapp/admin/prompt/history` — история |

### worker.py — ежедневная сводка

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `run_daily_summary` | да | `(bot: Bot) -> None` | Полный цикл генерации и отправки ежедневной сводки |

### test_llm.py — тестовый скрипт LLM

Пустой модуль (без функций).

### test_worker.py — тестовый скрипт worker

| Функция | Async | Сигнатура | Описание |
|---------|-------|-----------|----------|
| `main` | да | `() -> None` | Ручной запуск сводки для тестирования |

---

## 3. HTTP-эндпоинты

### Веб-дашборд

| Метод | Путь | Обработчик | Доступ | Описание |
|-------|------|------------|--------|----------|
| GET | `/` | `handle_index` | публичный | Лента сводок (авторизованным — с дашбордом) |
| GET | `/auth/login` | `auth.handle_login_page` | публичный | Страница авторизации Telegram Login |
| GET | `/auth/callback` | `auth.handle_auth_callback` | публичный | Callback от Telegram после авторизации |
| POST | `/auth/logout` | `auth.handle_logout` | авторизованный | Выход, очистка сессии |

### Веб-дашборд: администрирование

| Метод | Путь | Обработчик | Доступ | Описание |
|-------|------|------------|--------|----------|
| GET | `/admin/stats` | `handle_admin_stats` | admin | Статистика в JSON |
| GET | `/admin/prompt` | `handle_admin_prompt` | admin | Текущий промпт + история |
| POST | `/admin/prompt` | `handle_admin_prompt_save` | admin | Сохранить новый промпт |
| POST | `/admin/prompt/reset` | `handle_admin_prompt_reset` | admin | Сброс промпта к дефолту |
| GET | `/admin/prompt/history` | `handle_admin_prompt_history` | admin | История версий промпта |

### Веб-дашборд: чат

| Метод | Путь | Обработчик | Доступ | Описание |
|-------|------|------------|--------|----------|
| GET | `/admin/chat/dialogs` | `handle_chat_dialogs_list` | dialog | Список диалогов пользователя |
| POST | `/admin/chat/dialogs` | `handle_chat_dialog_create` | dialog | Создать новый диалог |
| GET | `/admin/chat/dialogs/{id}/messages` | `handle_chat_messages_list` | dialog | История сообщений диалога |
| POST | `/admin/chat/dialogs/{id}/messages` | `handle_chat_message_send` | dialog | Отправить сообщение Лешему |

### Telegram Mini App

| Метод | Путь | Обработчик | Доступ | Описание |
|-------|------|------------|--------|----------|
| GET | `/miniapp/` | `miniapp_index` | публичный | Шелл Mini App (HTML) |
| POST | `/miniapp/auth` | `miniapp_auth` | публичный | Авторизация через initData |
| GET | `/miniapp/feed` | `miniapp_feed` | авторизованный | Лента сводок (JSON) |
| GET | `/miniapp/chat/dialogs` | `miniapp_chat_dialogs` | dialog | Список диалогов |
| POST | `/miniapp/chat/dialogs` | `miniapp_chat_create_dialog` | dialog | Создать диалог |
| GET | `/miniapp/chat/dialogs/{id}/messages` | `miniapp_chat_messages` | dialog | История сообщений |
| POST | `/miniapp/chat/dialogs/{id}/messages` | `miniapp_chat_send` | dialog | Отправить сообщение |
| GET | `/miniapp/admin/stats` | `miniapp_admin_stats` | admin | Статистика |
| GET | `/miniapp/admin/prompt` | `miniapp_admin_prompt_get` | admin | Оба промпта (сводок + чата) |
| POST | `/miniapp/admin/prompt` | `miniapp_admin_prompt_save` | admin | Сохранить промпт |
| POST | `/miniapp/admin/prompt/reset` | `miniapp_admin_prompt_reset` | admin | Сброс промпта |
| GET | `/miniapp/admin/prompt/history` | `miniapp_admin_prompt_history` | admin | История версий |

### Статика

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/static/` | Статические файлы (style.css и др.) |

Итого: 26 маршрутов + статика.

Уровни доступа: **публичный** — без проверки; **авторизованный** — Telegram Login или initData; **dialog** — `DIALOG_ALLOWED_IDS`; **admin** — `ADMIN_IDS`.

---

## 4. Telegram-хэндлеры

### Команды (ЛС)

| Фильтр | Обработчик | Описание |
|--------|------------|----------|
| `/start`, ЛС | `cmd_start` | Приветствие + постоянная клавиатура |
| `/new`, ЛС | `cmd_new` | Создать новый диалог |
| `/dialogs`, ЛС | `cmd_dialogs` | Список диалогов |
| `/export`, ЛС | `cmd_export` | Экспорт текущего диалога |
| `/delete`, ЛС | `cmd_delete` | Удалить текущий диалог |
| `/deleteall`, ЛС | `cmd_deleteall` | Удалить все диалоги |

Все команды требуют `DIALOG_ALLOWED_IDS`.

### Текстовые кнопки (ReplyKeyboard, ЛС)

| Фильтр | Обработчик | Описание |
|--------|------------|----------|
| `F.text == "Новый"`, ЛС | `btn_new` | Создать диалог |
| `F.text == "Диалоги"`, ЛС | `btn_dialogs` | Список диалогов с инлайн-кнопками |
| `F.text == "Помощь"`, ЛС | `btn_help` | Справка по командам |

Все кнопки требуют `DIALOG_ALLOWED_IDS`.

### Callback-хэндлеры (InlineKeyboard, ЛС)

| Фильтр | Обработчик | Описание |
|--------|------------|----------|
| `dlg_export:{id}` | `cb_export` | Экспорт конкретного диалога |
| `dlg_delete:{id}` | `cb_delete` | Запрос подтверждения удаления |
| `dlg_delete_yes:{id}` | `cb_delete_yes` | Подтверждение удаления |
| `dlg_delete_no:{id}` | `cb_delete_no` | Отмена удаления, восстановление кнопок |

Все callback требуют `DIALOG_ALLOWED_IDS`.

### Catch-all и групповой чат

| Фильтр | Обработчик | Контекст | Описание |
|--------|------------|----------|----------|
| `F.text`, ЛС | `handle_private_message` | ЛС | Любой текст → диалог с Лешим (catch-all) |
| `F.chat.type.in_(group, supergroup)` | `handle_message` | группа | Приём и сохранение сообщений |

`handle_private_message` требует `DIALOG_ALLOWED_IDS`. `handle_message` фильтрует по `ALLOWED_CHAT_ID`.

Итого: 15 хэндлеров (6 команд, 3 кнопки, 4 callback, 1 catch-all ЛС, 1 групповой).

---

## 5. База данных

SQLite, файл `taigabot.db`, режим WAL, foreign keys включены.

### Таблица `messages` — входящие сообщения

```sql
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   TEXT    NOT NULL,
    username  TEXT,
    text      TEXT    NOT NULL,
    timestamp INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
```

Временное хранилище. Пишет: `ingest.py` (при каждом сообщении). Читает: `worker.py` (при генерации сводки). Удаляет: `worker.py` (записи старше 48 часов после генерации сводки). `user_id` — анонимизированный хэш SHA256[:12].

### Таблица `summaries` — архив сводок

```sql
CREATE TABLE IF NOT EXISTS summaries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL UNIQUE,
    summary_text TEXT    NOT NULL,
    created_at   INTEGER NOT NULL
);
```

Постоянный архив. Пишет: `worker.py` (после генерации). Читает: `web_app.py` (лента, Mini App, статистика). Колонка `image_path TEXT` добавлена миграцией (ALTER TABLE). Не удаляется.

### Таблица `settings` — настройки (key-value)

```sql
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT    PRIMARY KEY,
    value      TEXT    NOT NULL,
    updated_at INTEGER NOT NULL
);
```

Хранит настраиваемые параметры: системные промпты (`system_prompt`, `chat_system_prompt`). Пишет: `web_app.py` (редактор промптов). Читает: `llm.py`, `chat.py` (при генерации). Удаляет: `web_app.py` (сброс к дефолту).

### Таблица `prompt_history` — история версий промптов

```sql
CREATE TABLE IF NOT EXISTS prompt_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_text TEXT    NOT NULL,
    changed_at  INTEGER NOT NULL,
    changed_by  TEXT
);
```

Аудит изменений промптов. Колонка `prompt_key TEXT DEFAULT 'system_prompt'` добавлена миграцией. Пишет: `web_app.py` (при сохранении/сбросе промпта). Читает: `web_app.py` (история в дашборде). Не удаляется.

### Таблица `dialogs` — диалоги с Лешим

```sql
CREATE TABLE IF NOT EXISTS dialogs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    title      TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dialogs_user ON dialogs(user_id);
```

Пишет: `dialog_handlers.py`, `web_app.py` (создание диалога). Читает: `dialog_handlers.py`, `web_app.py`, `chat.py`. Удаляет: `dialog_handlers.py` (команда /delete, /deleteall).

### Таблица `dialog_messages` — сообщения в диалогах

```sql
CREATE TABLE IF NOT EXISTS dialog_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dialog_id  INTEGER NOT NULL REFERENCES dialogs(id) ON DELETE CASCADE,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dm_dialog ON dialog_messages(dialog_id);
```

Каскадное удаление при удалении диалога. Пишет: `chat.py` (сообщения пользователя и Лешего). Читает: `chat.py` (контекст для LLM), `dialog_handlers.py` (экспорт), `web_app.py` (API). `role`: `user` или `assistant`.

### PRAGMA

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
```

Итого: 6 таблиц, 4 индекса, 2 миграции (ALTER TABLE).

---

## 6. Переменные окружения

### Обязательные

| Переменная | Описание | Пример | Модули |
|------------|----------|--------|--------|
| `BOT_TOKEN` | Токен Telegram-бота от BotFather | `123456:ABC-DEF...` | config, bot, auth |
| `ALLOWED_CHAT_ID` | ID группового чата (отрицательное число) | `-1001234567890` | config, ingest |
| `ADMIN_IDS` | Telegram ID администраторов через запятую | `123456789,987654321` | config, auth, web_app |
| `OPENAI_API_KEY` | Ключ OpenAI API | `sk-...` | config, llm, imagegen |
| `OPENAI_MODEL` | Модель для генерации сводок | `gpt-5.4-mini` | config, llm |
| `SUMMARY_TIME` | Время ежедневной сводки (HH:MM) | `22:00` | config, bot |
| `TIMEZONE` | Временная зона | `Europe/Riga` | config, bot |
| `SESSION_SECRET_KEY` | 32-байтный ключ Fernet для сессий | (генерируется) | config, web_app |
| `BOT_USERNAME` | @username бота без @ | `leshiy_v_taige_bot` | config, auth |
| `CHAT_API_BASE` | Base URL провайдера чата | `https://api.cerebras.ai/v1` | config, chat |
| `CHAT_API_KEY` | API-ключ провайдера чата | (ключ Cerebras) | config, chat |
| `CHAT_MODEL` | Модель для интерактивного чата | `qwen-3-235b-a22b-instruct-2507` | config, chat |

### Опциональные (есть defaults)

| Переменная | Default | Описание | Модули |
|------------|---------|----------|--------|
| `SUMMARY_CHAT_ID` | = `ALLOWED_CHAT_ID` | Куда отправлять сводки (если отличается от основного чата) | config, worker |
| `IMAGE_MODEL` | `gpt-image-1-mini` | Модель генерации картинок | config, imagegen |
| `IMAGE_QUALITY` | `low` | Качество картинки: low / medium / high | config, imagegen |
| `IMAGE_SIZE` | `1024x1024` | Размер картинки | config, imagegen |
| `WEB_PORT` | `8080` | Порт веб-сервера | config, bot |
| `DIALOG_ALLOWED_IDS` | (пусто = нет ограничений) | Telegram ID для доступа к чату с Лешим | config, dialog_handlers, web_app |

Вычисляемые: `BOT_ID` = числовая часть `BOT_TOKEN` до двоеточия.

---

## 7. Зависимости

| Пакет | Версия | Назначение | Модули |
|-------|--------|------------|--------|
| aiogram | 3.26.0 | Telegram Bot API (async) | bot, ingest, dialog_handlers |
| aiosqlite | 0.22.1 | Асинхронная работа с SQLite | database |
| openai | 2.29.0 | OpenAI API (Responses API, image gen) | llm, imagegen, chat |
| APScheduler | 3.11.2 | Планировщик ежедневных задач | bot |
| python-dotenv | 1.2.2 | Загрузка .env | config |
| Pillow | 12.1.1 | Наложение подписей на изображения | imagegen |
| aiohttp-jinja2 | 1.6 | Jinja2-интеграция для aiohttp | web_app |
| Jinja2 | 3.1.6 | Шаблонизатор HTML | web_app, templates |
| aiohttp-session | 2.12.1 | Управление сессиями (EncryptedCookieStorage) | web_app |
| PyJWT[crypto] | 2.12.1 | Валидация JWT от Telegram Login | auth |
| ddgs | ≥9.0.0 | DuckDuckGo поиск для чата | chat |

---

## 8. HTML-шаблоны

### base.html (1 127 байт) — базовый шаблон

Наследование: корневой (другие шаблоны используют `{% extends "base.html" %}`). Содержит навигацию, подключение `style.css`, блок `{% block content %}`. Встроенный JS: один `<script>` блок (навигация / UI).

### summaries.html (617 байт) — публичная лента сводок

Наследование: `{% extends "base.html" %}`. Условно включает dashboard.html для авторизованных (`{% if user %}`). Без собственных `<script>` блоков.

### dashboard.html (17 389 байт) — пульт администратора

Наследование: включается в summaries.html через `{% include %}`. Содержит карточку чата с Лешим, карточку статистики, редактор промптов (два таба: Сводки/Чат), аккордеон истории версий. Один `<script>` блок (~600 строк JS): инициализация чата, WebSocket-подобное взаимодействие, управление промптами, кеширование.

### login.html (1 641 байт) — страница авторизации

Наследование: standalone (не extends base.html). Подключает `telegram-widget.js` с `data-auth-url` (redirect-flow). Минимальный JS.

### miniapp.html (23 803 байт) — Telegram Mini App

Наследование: standalone. Подключает `telegram-web-app.js`. CSS использует Telegram CSS-переменные с fallback. Два `<script>` блока: подключение Telegram SDK, основной JS (~800 строк). JS организован в IIFE-блоки: авторизация (initData → POST /miniapp/auth), лента сводок, чат (ленивая инициализация, флаг `chatInitialized`), пульт админа (ленивая инициализация, флаг `adminInitialized`). Нижняя навигация по вкладкам.
