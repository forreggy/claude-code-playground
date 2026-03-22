"""Ежедневная задача: генерация хулиганской сводки и отправка в чат.

Запускается по расписанию через APScheduler. Алгоритм:
  1. Достать из messages все записи за последние 24 часа.
  2. Если меньше 10 сообщений — отправить заглушку, сводку не генерировать.
  3. Иначе — передать контекст в llm.generate_summary().
  4. Сохранить результат в summaries.
  5. Отправить текст сводки в ALLOWED_CHAT_ID.
  6. Удалить из messages записи старше 48 часов.

При ошибках на шагах 3–5 повторяет попытку каждую минуту до успеха.
"""

import asyncio
import datetime
import logging
import time

from aiogram import Bot

import config
import database
import imagegen
import llm

logger = logging.getLogger(__name__)

_QUIET_DAY_TEXT = "Сегодня в чате было тихо. Даже Леший не вышел."
_MIN_MESSAGES = 10
_RETRY_INTERVAL = 60
_IMAGE_RETRY_INTERVAL = 30
_IMAGE_MAX_ATTEMPTS = 3
_CLEANUP_AGE = 48 * 3600  # 48 часов в секундах


async def run_daily_summary(bot: Bot) -> None:
    """Выполнить полный цикл генерации и отправки ежедневной сводки.

    Получает сообщения за последние 24 часа, генерирует сводку через LLM,
    сохраняет в БД и отправляет в чат. При ошибках на этапах генерации/отправки
    повторяет попытку каждые 60 секунд. После успеха чистит старые сообщения.
    """
    since_ts = int(time.time()) - 86400
    messages = await database.get_messages_since(since_ts)

    logger.info("Сообщений за последние 24 часа: %d", len(messages))

    if len(messages) < _MIN_MESSAGES:
        logger.info(
            "Сообщений недостаточно (%d < %d), отправляем заглушку",
            len(messages),
            _MIN_MESSAGES,
        )
        await bot.send_message(config.ALLOWED_CHAT_ID, _QUIET_DAY_TEXT)
        return

    messages_for_llm = [{"username": m["username"], "text": m["text"]} for m in messages]
    date_str = datetime.date.today().isoformat()

    while True:
        try:
            summary = await llm.generate_summary(messages_for_llm)
            parsed = llm.parse_summary_response(summary)

            # Попытка сгенерировать и отправить картинку (не блокирует текст)
            if parsed["image_prompt"] and parsed["image_caption"]:
                photo = None
                for attempt in range(_IMAGE_MAX_ATTEMPTS):
                    photo = await imagegen.generate_meme_image(
                        parsed["image_prompt"], parsed["image_caption"]
                    )
                    if photo:
                        break
                    if attempt < _IMAGE_MAX_ATTEMPTS - 1:
                        logger.warning(
                            "Попытка %d/%d генерации картинки не удалась, повтор через %d сек",
                            attempt + 1,
                            _IMAGE_MAX_ATTEMPTS,
                            _IMAGE_RETRY_INTERVAL,
                        )
                        await asyncio.sleep(_IMAGE_RETRY_INTERVAL)

                if photo:
                    await bot.send_photo(config.ALLOWED_CHAT_ID, photo=photo)
                    logger.info("Картинка МЕМ ДНЯ отправлена")
                else:
                    logger.warning("Не удалось сгенерировать картинку за %d попыток", _IMAGE_MAX_ATTEMPTS)

            # Текстовая сводка отправляется ВСЕГДА
            created_at = int(time.time())
            await database.save_summary(date_str, summary, created_at)
            await bot.send_message(
                config.ALLOWED_CHAT_ID, parsed["summary_text"], parse_mode="HTML"
            )
            logger.info("Сводка за %s успешно отправлена", date_str)
            break
        except Exception:
            logger.error(
                "Ошибка при генерации/отправке сводки, повтор через %d сек",
                _RETRY_INTERVAL,
                exc_info=True,
            )
            await asyncio.sleep(_RETRY_INTERVAL)

    cleanup_ts = int(time.time()) - _CLEANUP_AGE
    await database.delete_messages_older_than(cleanup_ts)
