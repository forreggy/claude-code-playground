"""Инициализация SQLite-базы данных и все SQL-запросы (CRUD).

База данных хранится в файле taigabot.db рядом со скриптом.
При старте бота вызывается init_db(), которая создаёт таблицы если их нет
и настраивает WAL-режим для безопасной параллельной записи.

Таблицы:
  messages  — входящие сообщения (временное хранилище, чистится каждые 48 ч)
  summaries — архив готовых сводок (не удаляется)
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

        await db.commit()

        # Миграция: добавить столбец image_path в summaries если его нет
        cursor = await db.execute("PRAGMA table_info(summaries)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "image_path" not in columns:
            await db.execute("ALTER TABLE summaries ADD COLUMN image_path TEXT")
            await db.commit()
            logger.info("Миграция: добавлен столбец image_path в summaries")

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


async def delete_messages_older_than(ts: int) -> None:
    """Удалить из таблицы messages все записи с timestamp < ts."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM messages WHERE timestamp < ?",
            (ts,),
        )
        await db.commit()
    logger.info("Удалено %d старых сообщений (старше timestamp=%d)", cursor.rowcount, ts)
