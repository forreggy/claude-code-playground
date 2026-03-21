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

    logger.info("База данных инициализирована: %s", DB_PATH)


async def save_message(
    user_id: str,
    username: str | None,
    text: str,
    timestamp: int,
) -> None:
    """Сохранить входящее сообщение в таблицу messages."""
    # TODO: реализовать
    pass


async def get_messages_since(since_ts: int) -> list[dict]:
    """Вернуть все сообщения с timestamp >= since_ts.

    Каждый элемент списка — словарь с ключами username и text.
    """
    # TODO: реализовать
    pass


async def save_summary(date: str, summary_text: str, created_at: int) -> None:
    """Сохранить готовую сводку в таблицу summaries.

    Args:
        date: дата в формате YYYY-MM-DD
        summary_text: полный текст сводки
        created_at: Unix timestamp момента генерации
    """
    # TODO: реализовать
    pass


async def delete_messages_older_than(ts: int) -> None:
    """Удалить из таблицы messages все записи с timestamp < ts."""
    # TODO: реализовать
    pass
