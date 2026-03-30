"""Хэндлеры диалогов: приём личных сообщений и чат с Лешим."""

import asyncio
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

import config
import database
from chat import chat_with_leshy

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("new"), F.chat.type == "private")
async def cmd_new(message: Message) -> None:
    """Создать новый диалог, предыдущий остаётся в истории."""
    if message.from_user.id not in config.DIALOG_ALLOWED_IDS:
        return
    await database.create_dialog(message.from_user.id)
    await message.answer("Новый диалог начат.")


@router.message(Command("dialogs"), F.chat.type == "private")
async def cmd_dialogs(message: Message) -> None:
    """Показать список всех диалогов пользователя."""
    user_id: int = message.from_user.id
    if user_id not in config.DIALOG_ALLOWED_IDS:
        return
    dialogs = await database.get_dialogs(user_id)
    if not dialogs:
        await message.answer("Диалогов пока нет.")
        return
    lines = []
    for i, d in enumerate(dialogs, 1):
        date_str = datetime.fromtimestamp(d["created_at"]).strftime("%d.%m.%Y")
        msgs = await database.get_dialog_messages(d["id"])
        lines.append(f"{i}. {date_str} — {len(msgs)} сообщений")
    await message.answer("\n".join(lines))


@router.message(Command("export"), F.chat.type == "private")
async def cmd_export(message: Message) -> None:
    """Выгрузить текущий диалог текстом в формате [роль] текст."""
    user_id: int = message.from_user.id
    if user_id not in config.DIALOG_ALLOWED_IDS:
        return
    dialogs = await database.get_dialogs(user_id)
    if not dialogs:
        await message.answer("Нет активного диалога.")
        return
    msgs = await database.get_all_dialog_messages(dialogs[0]["id"])
    lines = [f"[{m['role']}] {m['content']}" for m in msgs]
    await message.answer("\n".join(lines) if lines else "(пустой диалог)")


@router.message(Command("delete"), F.chat.type == "private")
async def cmd_delete(message: Message) -> None:
    """Удалить текущий диалог (последний по updated_at)."""
    user_id: int = message.from_user.id
    if user_id not in config.DIALOG_ALLOWED_IDS:
        return
    dialogs = await database.get_dialogs(user_id)
    if not dialogs:
        await message.answer("Нет активного диалога.")
        return
    await database.delete_dialog(dialogs[0]["id"])
    await message.answer("Диалог удалён.")


@router.message(Command("deleteall"), F.chat.type == "private")
async def cmd_deleteall(message: Message) -> None:
    """Удалить все диалоги пользователя."""
    user_id: int = message.from_user.id
    if user_id not in config.DIALOG_ALLOWED_IDS:
        return
    dialogs = await database.get_dialogs(user_id)
    if not dialogs:
        await message.answer("Диалогов нет.")
        return
    await database.delete_all_dialogs(user_id)
    await message.answer("Все диалоги удалены.")


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
