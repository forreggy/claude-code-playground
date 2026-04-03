# CLAUDE.md — TaigaBot Lite

## Правила для агента (ОБЯЗАТЕЛЬНЫЕ, нарушение недопустимо)

**ВЕТКА.** Если в задаче указана существующая ветка — выполни
`git fetch origin && git checkout имя-ветки`. Если ветки нет —
сообщи об этом. ЗАПРЕЩЕНО создавать новую ветку если задача
этого явно не требует.

**ДЕЙСТВУЙ.** Выполняй задачу немедленно. ЗАПРЕЩЕНО спрашивать
разрешение на создание файлов, запуск команд или выполнение
шагов, описанных в задаче. Задача = разрешение.

**ЭКОНОМЬ ТОКЕНЫ.** Если задача указывает конкретные файлы-источники —
читай только их. ЗАПРЕЩЕНО читать весь проект «для контекста».

**ВЕРИФИЦИРУЙ.** После каждого шага изменения файла — проверяй
результат через `grep` или `cat`. Покажи вывод. Если результат
не совпадает с ожиданием — исправь до перехода к следующему шагу.

**КОММИТЬ И ПУШЬ.** После завершения задачи — `git add`, `commit`,
`push`. Без напоминаний.

---

## Проект

**TaigaBot Lite** («Леший») — Telegram-бот, который мониторит
групповой чат, генерирует ежедневные AI-сводки с мем-картинками,
и предоставляет интерактивный чат с персонажем Леший.

Четыре интерфейса: Telegram групповой чат, Telegram ЛС (личные
сообщения с кнопками), веб-дашборд (taiga.ex-mari.com), Telegram
Mini App.

**Репозиторий:** https://github.com/forreggy/claude-code-playground
**Деплой:** Ubuntu VPS, systemd, Python venv, nginx, Cloudflare
**Документация:** `docs/inventory.md` — полный реестр проекта

---

## Стек

- Python 3.11+, async/await
- aiogram 3.x — Telegram Bot API
- aiosqlite — SQLite (WAL mode)
- openai SDK — Responses API (сводки, картинки), Chat Completions (чат)
- APScheduler — ежедневные задачи
- aiohttp + Jinja2 — веб-сервер и шаблоны
- aiohttp-session (Fernet) — сессии
- PyJWT[crypto] — Telegram Login
- Pillow — наложение подписей на картинки
- ddgs — DuckDuckGo поиск для чата

Никаких ORM. Никакого Docker. Только чистый SQL через aiosqlite.

---

## Структура файлов

```
├── bot.py              — точка входа: polling + scheduler + web-сервер
├── config.py           — загрузка .env, валидация
├── database.py         — все SQL-запросы, 6 таблиц, миграции
├── ingest.py           — приём сообщений из группового чата
├── worker.py           — ежедневная сводка: LLM → картинка → отправка
├── llm.py              — OpenAI Responses API, промпт сводок, парсинг
├── chat.py             — чат с Лешим (Cerebras, агентный цикл, web search)
├── imagegen.py         — генерация картинок (OpenAI Image API + Pillow)
├── auth.py             — Telegram Login (JWT), Mini App initData, middleware
├── dialog_handlers.py  — Telegram ЛС: команды, кнопки, callback, catch-all
├── web_app.py          — aiohttp: 26 маршрутов (дашборд + Mini App + API)
├── templates/          — 5 HTML-шаблонов (base, summaries, dashboard, login, miniapp)
├── static/style.css    — стили дашборда
├── docs/               — техническая документация
│   ├── inventory.md    — полный реестр проекта (модули, эндпоинты, БД, конфиг)
│   └── raw/            — сырые данные инвентаризации (скрипт + результаты)
├── test_llm.py         — тестовый скрипт LLM
├── test_worker.py      — тестовый скрипт worker
└── taigabot.service    — шаблон systemd unit
```

---

## БД (SQLite, taigabot.db)

6 таблиц: `messages` (входящие, временные), `summaries` (архив сводок),
`settings` (key-value, промпты), `prompt_history` (аудит промптов),
`dialogs` (диалоги с Лешим), `dialog_messages` (сообщения в диалогах,
CASCADE). Подробные DDL — в `docs/inventory.md`, раздел 5.

---

## Конфигурация (.env)

Обязательные: `BOT_TOKEN`, `ALLOWED_CHAT_ID`, `ADMIN_IDS`,
`OPENAI_API_KEY`, `OPENAI_MODEL`, `SUMMARY_TIME`, `TIMEZONE`,
`SESSION_SECRET_KEY`, `BOT_USERNAME`, `CHAT_API_BASE`, `CHAT_API_KEY`,
`CHAT_MODEL`.

Опциональные (есть defaults): `SUMMARY_CHAT_ID`, `IMAGE_MODEL`,
`IMAGE_QUALITY`, `IMAGE_SIZE`, `WEB_PORT`, `DIALOG_ALLOWED_IDS`.

Вычисляемые: `BOT_ID` = числовая часть `BOT_TOKEN` до двоеточия.

Полное описание — в `docs/inventory.md`, раздел 6.

---

## Два LLM-клиента (не путать!)

**llm.py** — OpenAI Responses API (`client.responses.create`),
`store=False`. Модель: `gpt-5.4-mini`. Для ежедневных сводок.

**chat.py** — Chat Completions API (`client.chat.completions.create`).
Провайдер: Cerebras. Модель: `qwen-3-235b-a22b-instruct-2507`.
Для интерактивного чата. Агентный цикл с tool calling (web search).

---

## Уровни доступа

- **Публичный** — лента сводок (`/`, `/miniapp/feed`)
- **dialog** — `DIALOG_ALLOWED_IDS` (чат с Лешим в ЛС, дашборде, Mini App)
- **admin** — `ADMIN_IDS` (статистика, редактор промптов, пульт)

---

## Правила разработки

- async/await для всего I/O
- Type hints обязательны
- Docstrings на русском
- Логирование: `logging`, INFO/ERROR
- Коммиты: `feat:`, `fix:`, `refactor:`, `docs:`
- ЗАПРЕЩЕНО: коммитить .env, taigabot.db; добавлять зависимости без согласования
- Приоритеты: работает корректно → читаемый код → производительность
- Не добавлять функциональность сверх задачи
- Не рефакторить то, чего задача не касается
