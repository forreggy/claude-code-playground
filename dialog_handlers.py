"""Хэндлеры диалогов: приём личных сообщений и чат с Лешим."""

import asyncio
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import config
import database
from chat import chat_with_leshy

logger = logging.getLogger(__name__)
router = Router()


def _main_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная ReplyKeyboard с тремя кнопками управления диалогами."""
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="Диалоги"),
            KeyboardButton(text="Новый"),
            KeyboardButton(text="Помощь"),
        ]],
        resize_keyboard=True,
        is_persistent=True,
    )


def _dialog_keyboard(dialog_id: int) -> InlineKeyboardMarkup:
    """Инлайн-кнопки для одного диалога: Экспорт и Удалить."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Экспорт", callback_data=f"dlg_export:{dialog_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"dlg_delete:{dialog_id}"),
    ]])


def _confirm_keyboard(dialog_id: int) -> InlineKeyboardMarkup:
    """Инлайн-кнопки подтверждения удаления диалога."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"dlg_delete_yes:{dialog_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"dlg_delete_no:{dialog_id}"),
    ]])


@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message) -> None:
    """Приветствие и выдача постоянной клавиатуры."""
    if message.from_user.id not in config.DIALOG_ALLOWED_IDS:
        return
    await message.answer(
        "Я — <b>Леший</b>, лесной дух этого чата 🌲\n\n"
        "Пиши — отвечу. Кнопки внизу помогут управлять диалогами.",
        parse_mode="HTML",
        reply_markup=_main_keyboard(),
    )


@router.message(Command("new"), F.chat.type == "private")
async def cmd_new(message: Message) -> None:
    """Создать новый диалог, предыдущий остаётся в истории."""
    if message.from_user.id not in config.DIALOG_ALLOWED_IDS:
        return
    await database.create_dialog(message.from_user.id)
    await message.answer("Новый диалог начат.", reply_markup=_main_keyboard())


@router.message(Command("dialogs"), F.chat.type == "private")
async def cmd_dialogs(message: Message) -> None:
    """Показать список всех диалогов пользователя."""
    user_id: int = message.from_user.id
    if user_id not in config.DIALOG_ALLOWED_IDS:
        return
    dialogs = await database.get_dialogs(user_id)
    if not dialogs:
        await message.answer("Диалогов пока нет.", reply_markup=_main_keyboard())
        return
    lines = []
    for i, d in enumerate(dialogs, 1):
        date_str = datetime.fromtimestamp(d["created_at"]).strftime("%d.%m.%Y")
        msgs = await database.get_dialog_messages(d["id"])
        lines.append(f"{i}. {date_str} — {len(msgs)} сообщений")
    await message.answer("\n".join(lines), reply_markup=_main_keyboard())


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


@router.message(F.chat.type == "private", F.text == "Новый")
async def btn_new(message: Message) -> None:
    """Кнопка «Новый»: создать новый диалог."""
    if message.from_user.id not in config.DIALOG_ALLOWED_IDS:
        return
    await database.create_dialog(message.from_user.id)
    await message.answer("Новый диалог начат.", reply_markup=_main_keyboard())


@router.message(F.chat.type == "private", F.text == "Диалоги")
async def btn_dialogs(message: Message) -> None:
    """Кнопка «Диалоги»: список диалогов с инлайн-кнопками управления."""
    user_id: int = message.from_user.id
    if user_id not in config.DIALOG_ALLOWED_IDS:
        return
    dialogs = await database.get_dialogs(user_id)
    if not dialogs:
        await message.answer("Диалогов пока нет. Напиши что-нибудь!")
        return
    for d in dialogs:
        date_str = datetime.fromtimestamp(d["created_at"]).strftime("%d.%m.%Y")
        msgs = await database.get_dialog_messages(d["id"])
        text = f"📁 Диалог от {date_str}, {len(msgs)} сообщений"
        await message.answer(text, reply_markup=_dialog_keyboard(d["id"]))


@router.message(F.chat.type == "private", F.text == "Помощь")
async def btn_help(message: Message) -> None:
    """Кнопка «Помощь»: справка по командам."""
    if message.from_user.id not in config.DIALOG_ALLOWED_IDS:
        return
    await message.answer(
        "<b>Управление диалогами</b>\n\n"
        "• <b>Новый</b> — начать новый диалог\n"
        "• <b>Диалоги</b> — список диалогов с кнопками управления\n"
        "• /export — выгрузить текущий диалог\n"
        "• /deleteall — удалить все диалоги",
        parse_mode="HTML",
        reply_markup=_main_keyboard(),
    )


@router.callback_query(F.data.startswith("dlg_export:"))
async def cb_export(callback: CallbackQuery) -> None:
    """Callback: экспорт диалога в текст."""
    dialog_id = int(callback.data.split(":")[1])
    if callback.from_user.id not in config.DIALOG_ALLOWED_IDS:
        await callback.answer()
        return
    dialog = await database.get_dialog(dialog_id)
    if not dialog or dialog["user_id"] != callback.from_user.id:
        await callback.answer("Диалог не найден.")
        return
    msgs = await database.get_all_dialog_messages(dialog_id)
    lines = [f"[{m['role']}] {m['content']}" for m in msgs]
    await callback.message.answer("\n".join(lines) if lines else "(пустой диалог)", parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("dlg_delete:"))
async def cb_delete(callback: CallbackQuery) -> None:
    """Callback: запрос подтверждения удаления диалога."""
    dialog_id = int(callback.data.split(":")[1])
    if callback.from_user.id not in config.DIALOG_ALLOWED_IDS:
        await callback.answer()
        return
    dialog = await database.get_dialog(dialog_id)
    if not dialog or dialog["user_id"] != callback.from_user.id:
        await callback.answer("Диалог не найден.")
        return
    await callback.message.edit_reply_markup(reply_markup=_confirm_keyboard(dialog_id))
    await callback.answer()


@router.callback_query(F.data.startswith("dlg_delete_yes:"))
async def cb_delete_yes(callback: CallbackQuery) -> None:
    """Callback: подтверждение удаления — удалить диалог."""
    dialog_id = int(callback.data.split(":")[1])
    if callback.from_user.id not in config.DIALOG_ALLOWED_IDS:
        await callback.answer()
        return
    dialog = await database.get_dialog(dialog_id)
    if not dialog or dialog["user_id"] != callback.from_user.id:
        await callback.answer("Диалог не найден.")
        return
    await database.delete_dialog(dialog_id)
    await callback.message.delete()
    await callback.message.answer("Диалог удалён.")
    await callback.answer()


@router.callback_query(F.data.startswith("dlg_delete_no:"))
async def cb_delete_no(callback: CallbackQuery) -> None:
    """Callback: отмена удаления — восстановить кнопки Экспорт/Удалить."""
    dialog_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=_dialog_keyboard(dialog_id))
    await callback.answer("Отменено.")


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
