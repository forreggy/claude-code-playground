"""Точка входа: запуск Telegram-бота.

Инициализирует базу данных, регистрирует хэндлеры из ingest,
затем стартует aiogram polling.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher

import config
import database
import ingest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Инициализировать бота и запустить polling."""
    await database.init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(ingest.router)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
