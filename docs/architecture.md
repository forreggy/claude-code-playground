# Архитектура TaigaBot Lite

## 1. Обзор системы

TaigaBot Lite («Леший») — Telegram-бот, который мониторит сообщения в групповом
чате, раз в сутки генерирует AI-сводку дня с мем-картинкой и рассылает её
обратно в группу, а также предоставляет интерактивный чат с персонажем Леший
в четырёх интерфейсах: Telegram группа (источник сообщений и получатель
сводок), Telegram ЛС (чат через кнопки и команды), веб-дашборд
(taiga.ex-mari.com, браузерный интерфейс с авторизацией через Telegram Login
Widget) и Telegram Mini App (встроенное веб-приложение внутри Telegram).

Для генерации сводок и картинок используется OpenAI (Responses API и Image
API), для интерактивного чата — Cerebras (Chat Completions API, модель Qwen).
Это разделение позволяет использовать дорогостоящий пакетный LLM для сводок
и низколатентный провайдер для диалога в реальном времени.

---

## 2. Компоненты и их связи

### Точка входа

**`bot.py`** — единственная точка запуска всей системы. Функция `main()`
последовательно инициализирует базу данных, регистрирует Telegram-роутеры
(`ingest`, `dialog_handlers`), настраивает APScheduler для ежедневного запуска
worker, создаёт и запускает aiohttp-приложение из `web_app.py` на
`127.0.0.1:8080`, после чего стартует Telegram polling. Все компоненты
работают в одном event loop asyncio. Вызывает: `database.init_db`,
`ingest`, `dialog_handlers`, `worker.run_daily_summary`,
`web_app.create_web_app`. Не вызывается другими модулями проекта.

### Данные

**`config.py`** — загружает переменные окружения из `.env` при импорте и
предоставляет их остальным модулям как модульные константы: строки, числа,
frozenset. Не содержит async-кода и не имеет зависимостей от других модулей
проекта. Импортируется всеми модулями, которым нужны токены, идентификаторы
чатов или прочие настройки среды.

**`database.py`** — единственная точка доступа к SQLite. Содержит все
SQL-запросы в виде async-функций: создание, чтение и удаление записей для
всех шести таблиц (`messages`, `summaries`, `settings`, `prompt_history`,
`dialogs`, `dialog_messages`). Функция `init_db()` при старте применяет PRAGMA
(WAL mode, foreign keys) и накатывает миграции. Вызывается из всех модулей,
которые работают с данными: `bot.py`, `ingest.py`, `worker.py`, `llm.py`,
`chat.py`, `dialog_handlers.py`, `web_app.py`. Сам использует только
`config.py` для получения пути к файлу БД.

### Telegram

**`ingest.py`** — aiogram-роутер, слушающий групповой чат
(`chat.type in {group, supergroup}`). Единственная функция `handle_message`
принимает каждое текстовое сообщение и записывает его в таблицу `messages`
(user_id, username, text, unix timestamp) через `database.save_message`.
Является источником сырых данных для последующей генерации сводок.
Вызывает `database`. Регистрируется в `bot.py`.

**`dialog_handlers.py`** — aiogram-роутер для личных сообщений
(`chat.type == 'private'`). Обрабатывает команды (`/start`, `/new`,
`/dialogs`, `/export`, `/delete`, `/deleteall`), кнопки постоянной
клавиатуры («Новый», «Диалоги», «Помощь») и callback-запросы inline-кнопок
(экспорт и удаление диалогов). Catch-all хэндлер `handle_private_message`
принимает произвольный текст, находит или создаёт диалог в БД и передаёт
сообщение в `chat.chat_with_leshy`, отображая индикатор набора текста
(typing action) во время ожидания ответа. Вызывает `database`, `chat`.
Регистрируется в `bot.py`.

### AI

**`llm.py`** — генерирует ежедневные текстовые сводки через OpenAI Responses
API (`client.responses.create`, `store=False`). Функция `generate_summary`
принимает список словарей сообщений и возвращает структурированный текст.
Функция `parse_summary_response` разбирает ответ LLM, извлекая `image_prompt`,
`image_caption` и текст сводки — разделённые данные передаются в `imagegen.py`.
Читает актуальный системный промпт из таблицы `settings` через
`database.get_setting`. Вызывается исключительно из `worker.py`.

**`chat.py`** — обеспечивает интерактивный диалог с персонажем Леший через
Cerebras Chat Completions API. Функция `chat_with_leshy` загружает историю
диалога из БД, формирует контекст, запускает агентный цикл с tool calling:
если модель решает воспользоваться инструментом web_search, синхронная
функция `execute_web_search` делает запрос к DuckDuckGo через библиотеку
`ddgs` и возвращает результаты в следующем туре. Итоговый ответ сохраняется
в `dialog_messages` и возвращается вызывающей стороне. Системный промпт
читается из `settings` через `database.get_setting`. Вызывается из
`dialog_handlers.py` и `web_app.py`.

**`imagegen.py`** — генерирует мем-картинки к сводкам. Функция
`generate_meme_image` запрашивает изображение у OpenAI Image API по промпту,
а затем через внутреннюю функцию `_overlay_caption` (Pillow) накладывает
текстовую подпись на полупрозрачную плашку в нижней части картинки.
Возвращает `io.BytesIO` с готовым изображением или `None` при ошибке.
Вызывается исключительно из `worker.py`.

**`worker.py`** — оркестрирует полный цикл ежедневной сводки. Функция
`run_daily_summary` читает накопленные сообщения из БД, передаёт их в
`llm.generate_summary`, затем вызывает `imagegen.generate_meme_image`,
отправляет текст и картинку в Telegram-группу через объект `Bot`, сохраняет
запись в таблицу `summaries` и удаляет обработанные записи из `messages`.
Запускается по расписанию из `bot.py` через APScheduler. Вызывает
`database`, `llm`, `imagegen`.

### Веб

**`web_app.py`** — aiohttp-приложение с 26 маршрутами, организованными
в три группы: публичная лента сводок (`/`, `/summaries`), дашборд
администратора (статистика, редактор промптов, чат с Лешим — требует
авторизации через Telegram Login) и Telegram Mini App (`/miniapp/*` —
авторизация через initData). Для браузерного интерфейса рендерит HTML
через Jinja2-шаблоны, для API-запросов Mini App возвращает JSON. Вызывает
`database`, `chat`, `auth`. Создаётся и запускается из `bot.py`.

**`auth.py`** — реализует три механизма авторизации. Telegram Login Widget:
JWT через PyJWT (`_validate_jwt`) и legacy hash-based проверка
(`_validate_legacy_hash`). Mini App: HMAC-SHA256 по спецификации Telegram
(`validate_mini_app_init_data`). Middleware `auth_middleware` расшифровывает
Fernet-сессию и помещает данные пользователя в `request['user']` перед
каждым обработчиком. Хэндлеры `/auth/login`, `/auth/callback`,
`/auth/logout` регистрируются маршрутами в `web_app.py`. Вызывает
`config.py` для токенов и секретных ключей.

---

## 3. Потоки данных

**Поток 1 — Ежедневная сводка.** Каждое текстовое сообщение в группе
поступает в Telegram polling и попадает в хэндлер `ingest.handle_message`,
который сохраняет его в таблицу `messages` с unix-timestamp. В запланированное
время APScheduler вызывает `worker.run_daily_summary`, передавая объект `Bot`.
Worker запрашивает у `database` все сообщения за прошедшие сутки и передаёт
их список в `llm.generate_summary`. LLM возвращает структурированный текст,
который `llm.parse_summary_response` разбирает на три части: промпт для
картинки, подпись и текст сводки. Промпт и подпись передаются в
`imagegen.generate_meme_image`, которая получает изображение от OpenAI
Image API и накладывает подпись через Pillow. Worker отправляет текст
и картинку в Telegram-группу через Bot API, сохраняет запись в таблицу
`summaries` и удаляет обработанные `messages`.

**Поток 2 — Чат с Лешим.** Личное сообщение от пользователя попадает в
хэндлер `dialog_handlers.handle_private_message`. Хэндлер проверяет, входит
ли отправитель в `DIALOG_ALLOWED_IDS`; если да — находит последний активный
диалог пользователя или создаёт новый через `database.create_dialog`. Текст
сообщения передаётся в `chat.chat_with_leshy(dialog_id, user_message)`.
Функция загружает полную историю диалога из `dialog_messages`, добавляет
новое сообщение пользователя, отправляет весь контекст на Cerebras API.
Если модель запрашивает инструмент web_search — `chat.execute_web_search`
делает запрос к DuckDuckGo и результаты возвращаются в следующем туре
агентного цикла. Итоговый ответ сохраняется в `dialog_messages` и
возвращается пользователю в ЛС. Аналогичный путь проходят сообщения через
веб-дашборд и Mini App — только вместо Telegram-хэндлера входной точкой
служат `web_app.handle_chat_message_send` или `web_app.miniapp_chat_send`.

**Поток 3 — Веб-интерфейсы.** Браузерный запрос проходит через nginx
(reverse proxy с SSL), который проксирует его на `127.0.0.1:8080` к aiohttp.
Middleware `auth.auth_middleware` проверяет сессионную cookie (Fernet),
расшифровывает и помещает данные пользователя в `request['user']`. Обработчик
в `web_app.py` проверяет уровень доступа (публичный / dialog / admin по
`DIALOG_ALLOWED_IDS` и `ADMIN_IDS`), запрашивает данные у `database` и
либо рендерит HTML через Jinja2-шаблон (`summaries.html`, `dashboard.html`),
либо возвращает JSON для Mini App. Авторизация через Telegram Login Widget
идёт через `/auth/callback`: `auth._validate_jwt` или
`auth._validate_legacy_hash` верифицирует данные от Telegram, после чего
данные пользователя записываются в зашифрованный Fernet-cookie.

---

## 4. Схема запуска

При выполнении `systemctl start taigabot` systemd запускает `python bot.py`.
Функция `main()` первым делом вызывает `database.init_db()` — создаются
таблицы, применяются PRAGMA (WAL mode, foreign keys) и миграции схемы.
Затем к глобальному Dispatcher aiogram подключаются два роутера:
`ingest.router` (групповой чат) и `dialog_handlers.router` (ЛС).

APScheduler настраивается с часовым поясом из конфига (`TIMEZONE`) и
получает задачу `run_daily_summary` по cron-выражению из `SUMMARY_TIME`.
После этого `web_app.create_web_app()` собирает aiohttp-приложение:
регистрирует все 26 маршрутов, подключает `auth_middleware`, настраивает
Jinja2-окружение для шаблонов и aiohttp-session (ключ Fernet из
`SESSION_SECRET_KEY`). Веб-приложение запускается как фоновая async-задача
на `127.0.0.1:8080`. Последним запускается `dp.start_polling(bot)` —
с этого момента бот начинает принимать обновления от Telegram.

---

## 5. Инфраструктура

Проект развёрнут на VPS под управлением Ubuntu. Процесс управляется
systemd-юнитом (`taigabot.service`) — обеспечивается автозапуск при загрузке
сервера и автоматический перезапуск при падении. Python-зависимости
изолированы в виртуальном окружении (venv), версии зафиксированы в
`requirements.txt`.

Перед ботом стоит nginx в роли reverse proxy: принимает HTTPS-запросы на
`taiga.ex-mari.com` (порт 443), терминирует SSL и проксирует трафик на
`127.0.0.1:8080`. TLS-сертификат выдан Let's Encrypt и обновляется
автоматически через certbot. DNS и внешний кеш управляются Cloudflare —
CDN проксирует запросы, защищает от DDoS и скрывает реальный IP сервера.
Статика (`static/style.css`) отдаётся непосредственно aiohttp без
отдельного location в nginx.

Полная спецификация модулей, HTTP-эндпоинтов, Telegram-хэндлеров, схемы
БД и переменных окружения — в `docs/inventory.md`.
