"""Точка входа: запуск Telegram-бота.

Инициализирует базу данных, регистрирует хэндлеры из ingest,
настраивает APScheduler для ежедневной генерации сводки,
затем стартует aiogram polling и планировщик одновременно.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import database
import ingest
import worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Инициализировать бота, запустить scheduler и polling."""
    await database.init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(ingest.router)

    hour, minute = map(int, config.SUMMARY_TIME.split(":"))

    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(
        worker.run_daily_summary,
        CronTrigger(hour=hour, minute=minute, timezone=config.TIMEZONE),
        args=[bot],
    )

    scheduler.start()
    logger.info(
        "Scheduler запущен. Сводка будет генерироваться в %s (%s)",
        config.SUMMARY_TIME,
        config.TIMEZONE,
    )

    try:
        logger.info("Бот запущен, начинаю polling")
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        logger.info("Scheduler остановлен")


if __name__ == "__main__":
    asyncio.run(main())
