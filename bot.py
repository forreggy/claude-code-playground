"""Точка входа: запуск Telegram-бота и веб-сервера.

Инициализирует базу данных, регистрирует хэндлеры из ingest,
настраивает APScheduler для ежедневной генерации сводки,
запускает aiohttp веб-сервер для публичной ленты сводок,
затем стартует aiogram polling. Веб-сервер и polling работают
параллельно в одном event loop.
"""

import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import database
import dialog_handlers
import ingest
import worker
from web_app import create_web_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Инициализировать бота, запустить web-сервер, scheduler и polling."""
    await database.init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(ingest.router)
    dp.include_router(dialog_handlers.router)

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

    # Запуск веб-сервера (non-blocking, работает в фоне event loop)
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", config.WEB_PORT)
    await site.start()
    logger.info("Веб-лента запущена на порту %d", config.WEB_PORT)

    try:
        logger.info("Бот запущен, начинаю polling")
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        scheduler.shutdown()
        logger.info("Web-сервер и scheduler остановлены")


if __name__ == "__main__":
    asyncio.run(main())
