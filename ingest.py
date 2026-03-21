"""Приём и сохранение входящих сообщений из Telegram.

Содержит aiogram-хэндлер, который:
  — принимает только текстовые сообщения из ALLOWED_CHAT_ID (остальные игнорирует молча)
  — анонимизирует user_id через SHA256[:12]
  — сохраняет сообщение в базу данных через database.save_message()
"""

import hashlib
import logging

from aiogram import Router
from aiogram.types import Message

import config
import database

logger = logging.getLogger(__name__)

router = Router()


@router.message()
async def handle_message(message: Message) -> None:
    """Принять текстовое сообщение и сохранить в базу данных."""
    if message.chat.id != config.ALLOWED_CHAT_ID:
        return

    text = message.text or message.caption
    if not text:
        return
    if message.from_user is None:
        return

    user_id = hashlib.sha256(str(message.from_user.id).encode()).hexdigest()[:12]
    username = message.from_user.username
    timestamp = int(message.date.timestamp())

    await database.save_message(
        user_id=user_id,
        username=username,
        text=text,
        timestamp=timestamp,
    )
    logger.info("Принято сообщение от %s (@%s)", user_id, username)
