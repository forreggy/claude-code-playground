"""Инициализация SQLite-базы данных и все SQL-запросы (CRUD).

База данных хранится в файле taigabot.db рядом со скриптом.
При старте бота вызывается init_db(), которая создаёт таблицы если их нет
и настраивает WAL-режим для безопасной параллельной записи.

Таблицы:
  messages       — входящие сообщения (временное хранилище, чистится каждые 48 ч)
  summaries      — архив готовых сводок (не удаляется)
  settings       — настройки в формате key-value (в т.ч. system_prompt)
  prompt_history — история версий системного промпта (с поддержкой prompt_key)
  dialogs        — диалоги чата с Лешим (TLL-06)
  dialog_messages — сообщения диалогов (TLL-06)
"""

import logging

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = "taigabot.db"


async def init_db() -> None:
    """Создать таблицы и индексы, настроить PRAGMA.

    Безопасно вызывать при каждом старте: использует IF NOT EXISTS.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT    NOT NULL,
                username  TEXT,
                text      TEXT    NOT NULL,
                timestamp INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                date         TEXT    NOT NULL UNIQUE,
                summary_text TEXT    NOT NULL,
                created_at   INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT    PRIMARY KEY,
                value      TEXT    NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS prompt_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_text TEXT    NOT NULL,
                changed_at  INTEGER NOT NULL,
                changed_by  TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS dialogs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                title      TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_dialogs_user ON dialogs(user_id)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS dialog_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                dialog_id  INTEGER NOT NULL REFERENCES dialogs(id) ON DELETE CASCADE,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_dm_dialog ON dialog_messages(dialog_id)
        """)

        await db.commit()

        # Миграция: добавить столбец image_path в summaries если его нет
        cursor = await db.execute("PRAGMA table_info(summaries)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "image_path" not in columns:
            await db.execute("ALTER TABLE summaries ADD COLUMN image_path TEXT")
            await db.commit()
            logger.info("Миграция: добавлен столбец image_path в summaries")

        # Миграция: добавить столбец prompt_key в prompt_history если его нет
        cursor = await db.execute("PRAGMA table_info(prompt_history)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "prompt_key" not in columns:
            await db.execute(
                "ALTER TABLE prompt_history ADD COLUMN prompt_key TEXT DEFAULT 'system_prompt'"
            )
            await db.commit()
            logger.info("Миграция: добавлен столбец prompt_key в prompt_history")

    logger.info("База данных инициализирована: %s", DB_PATH)


async def save_message(
    user_id: str,
    username: str | None,
    text: str,
    timestamp: int,
) -> None:
    """Сохранить входящее сообщение в таблицу messages."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (user_id, username, text, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, username, text, timestamp),
        )
        await db.commit()
    logger.info("Сообщение сохранено: user_id=%s, timestamp=%d", user_id, timestamp)


async def get_messages_since(since_ts: int) -> list[dict]:
    """Вернуть все сообщения с timestamp >= since_ts.

    Каждый элемент списка — словарь с ключами user_id, username, text, timestamp.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, username, text, timestamp FROM messages WHERE timestamp >= ?",
            (since_ts,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "text": row["text"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]


async def save_summary(
    date: str,
    summary_text: str,
    created_at: int,
    image_path: str | None = None,
) -> None:
    """Сохранить готовую сводку в таблицу summaries.

    Args:
        date: дата в формате YYYY-MM-DD
        summary_text: полный текст сводки
        created_at: Unix timestamp момента генерации
        image_path: относительный путь к картинке МЕМ ДНЯ или None
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO summaries (date, summary_text, created_at, image_path) VALUES (?, ?, ?, ?)",
            (date, summary_text, created_at, image_path),
        )
        await db.commit()
    logger.info("Сводка сохранена в summaries: date=%s", date)


async def get_summaries_for_feed(limit: int = 30, offset: int = 0) -> list[dict]:
    """Вернуть сводки в обратном хронологическом порядке для веб-ленты."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT date, summary_text, image_path, created_at "
            "FROM summaries ORDER BY date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [
            {
                "date": row["date"],
                "summary_text": row["summary_text"],
                "image_path": row["image_path"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]


async def get_all_summaries() -> list[dict]:
    """Вернуть все сводки в обратном хронологическом порядке для Mini App."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, date, summary_text, image_path, created_at "
            "FROM summaries ORDER BY date DESC"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "date": row["date"],
                "summary_text": row["summary_text"],
                "image_path": row["image_path"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]


async def delete_messages_older_than(ts: int) -> None:
    """Удалить из таблицы messages все записи с timestamp < ts."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM messages WHERE timestamp < ?",
            (ts,),
        )
        await db.commit()
    logger.info("Удалено %d старых сообщений (старше timestamp=%d)", cursor.rowcount, ts)


async def get_setting(key: str) -> str | None:
    """Получить значение настройки по ключу. Возвращает None если ключ не существует."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_setting(key: str, value: str, updated_at: int) -> None:
    """Установить значение настройки. INSERT OR REPLACE."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, updated_at),
        )
        await db.commit()


async def delete_setting(key: str) -> None:
    """Удалить настройку по ключу."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM settings WHERE key = ?", (key,))
        await db.commit()


async def get_prompt_history(
    limit: int = 20,
    prompt_key: str = "system_prompt",
) -> list[dict]:
    """Вернуть историю промптов в обратном хронологическом порядке.

    Каждый элемент: {"id": int, "prompt_text": str, "changed_at": int, "changed_by": str | None}
    Параметр prompt_key фильтрует по типу промпта (system_prompt, chat_system_prompt и т.д.).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, prompt_text, changed_at, changed_by FROM prompt_history "
            "WHERE prompt_key = ? ORDER BY changed_at DESC LIMIT ?",
            (prompt_key, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def save_prompt_history(
    prompt_text: str,
    changed_at: int,
    changed_by: str | None = None,
    prompt_key: str = "system_prompt",
) -> None:
    """Сохранить версию промпта в историю.

    Параметр prompt_key указывает тип промпта (system_prompt, chat_system_prompt и т.д.).
    Существующие вызовы без prompt_key продолжают работать через дефолтное значение.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO prompt_history (prompt_text, changed_at, changed_by, prompt_key) "
            "VALUES (?, ?, ?, ?)",
            (prompt_text, changed_at, changed_by, prompt_key),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Диалоги чата с Лешим (TLL-06)
# ---------------------------------------------------------------------------

async def create_dialog(user_id: int) -> int:
    """Создаёт новый диалог, возвращает его id."""
    now = int(__import__("time").time())
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO dialogs (user_id, created_at, updated_at) VALUES (?, ?, ?)",
            (user_id, now, now),
        )
        await db.commit()
        return cursor.lastrowid


async def get_dialogs(user_id: int) -> list[dict]:
    """Возвращает список диалогов пользователя, отсортированных по updated_at DESC.

    Каждый dict: {id, title, created_at, updated_at}.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, title, created_at, updated_at FROM dialogs "
            "WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_dialog(dialog_id: int) -> dict | None:
    """Возвращает метаданные одного диалога или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, user_id, title, created_at, updated_at FROM dialogs WHERE id = ?",
            (dialog_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_dialog(dialog_id: int) -> None:
    """Удаляет диалог и все его сообщения (CASCADE)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("DELETE FROM dialogs WHERE id = ?", (dialog_id,))
        await db.commit()


async def delete_all_dialogs(user_id: int) -> None:
    """Удаляет все диалоги пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("DELETE FROM dialogs WHERE user_id = ?", (user_id,))
        await db.commit()


async def update_dialog_timestamp(dialog_id: int) -> None:
    """Обновляет updated_at на текущее время."""
    now = int(__import__("time").time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE dialogs SET updated_at = ? WHERE id = ?",
            (now, dialog_id),
        )
        await db.commit()


async def update_dialog_title(dialog_id: int, title: str) -> None:
    """Устанавливает заголовок диалога."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE dialogs SET title = ? WHERE id = ?",
            (title, dialog_id),
        )
        await db.commit()


async def add_dialog_message(dialog_id: int, role: str, content: str) -> int:
    """Добавляет сообщение в диалог, возвращает id сообщения.

    role: 'user', 'assistant', 'system', 'tool'.
    """
    now = int(__import__("time").time())
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO dialog_messages (dialog_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (dialog_id, role, content, now),
        )
        await db.commit()
        return cursor.lastrowid


async def get_dialog_messages(
    dialog_id: int,
    limit: int | None = None,
) -> list[dict]:
    """Возвращает сообщения диалога, отсортированные по id ASC.

    Если limit задан — возвращает последние N сообщений (role IN ('user', 'assistant')).
    Каждый dict: {id, role, content, created_at}.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if limit is None:
            cursor = await db.execute(
                "SELECT id, role, content, created_at FROM dialog_messages "
                "WHERE dialog_id = ? ORDER BY id ASC",
                (dialog_id,),
            )
        else:
            # Берём последние N (user+assistant), затем возвращаем в хронологическом порядке
            cursor = await db.execute(
                "SELECT id, role, content, created_at FROM ("
                "  SELECT id, role, content, created_at FROM dialog_messages "
                "  WHERE dialog_id = ? AND role IN ('user', 'assistant') "
                "  ORDER BY id DESC LIMIT ?"
                ") ORDER BY id ASC",
                (dialog_id, limit),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_all_dialog_messages(dialog_id: int) -> list[dict]:
    """Возвращает ВСЕ сообщения диалога (для экспорта), отсортированные по id ASC.

    Каждый dict: {id, role, content, created_at}.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, role, content, created_at FROM dialog_messages "
            "WHERE dialog_id = ? ORDER BY id ASC",
            (dialog_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_stats() -> dict:
    """Собрать статистику из существующих таблиц.

    Возвращает:
    {
        "total_summaries": int,        — количество записей в summaries
        "last_summary_date": str|None, — дата последней сводки (YYYY-MM-DD) или None
        "first_summary_date": str|None,— дата первой сводки (начало наблюдений)
        "messages_in_buffer": int,     — количество записей в messages (ожидают сводку)
    }
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*), MAX(date), MIN(date) FROM summaries"
        )
        row = await cursor.fetchone()
        total = row[0]
        last_date = row[1]
        first_date = row[2]

        cursor = await db.execute("SELECT COUNT(*) FROM messages")
        buf_row = await cursor.fetchone()

    return {
        "total_summaries": total,
        "last_summary_date": last_date,
        "first_summary_date": first_date,
        "messages_in_buffer": buf_row[0],
    }
