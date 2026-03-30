"""Хэндлеры диалогов: приём личных сообщений и чат с Лешим."""

import asyncio
import logging

from aiogram import F, Router
from aiogram.types import Message

import config
import database
from chat import chat_with_leshy

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.chat.type == "private", F.text)
async def handle_private_message(message: Message) -> None:
    """Обработать входящее личное сообщение: найти/создать диалог, вызвать LLM, ответить."""
    user_id: int = message.from_user.id

    if user_id not in config.DIALOG_ALLOWED_IDS:
        return

    # Найти последний активный диалог или создать новый
    dialogs = await database.get_dialogs(user_id)
    dialog_id: int = dialogs[0]["id"] if dialogs else await database.create_dialog(user_id)

    # Конкурентный запуск: typing-цикл + вызов модели
    response_ready = asyncio.Event()

    async def typing_loop() -> None:
        """Повторять send_chat_action typing каждые 4 секунды до получения ответа."""
        while not response_ready.is_set():
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            try:
                await asyncio.wait_for(asyncio.shield(response_ready.wait()), timeout=4.0)
            except asyncio.TimeoutError:
                pass

    typing_task = asyncio.create_task(typing_loop())
    try:
        reply = await chat_with_leshy(dialog_id, message.text)
    finally:
        response_ready.set()
        await typing_task

    await message.answer(reply, parse_mode="HTML")
    logger.info("user_id=%d dialog_id=%d reply_len=%d", user_id, dialog_id, len(reply))
