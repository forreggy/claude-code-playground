"""Публичная веб-лента сводок TaigaBot Lite.

Предоставляет read-only веб-страницу с архивом сводок в обратном
хронологическом порядке. Каждая сводка отображается как карточка
с картинкой МЕМ ДНЯ (если есть) и текстом.

Авторизованные администраторы видят скелет дашборда над лентой.
"""

import datetime
import json
import logging
import pathlib
import time

import aiohttp_jinja2
import jinja2
from aiohttp import web
from aiohttp_session import setup as setup_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography.fernet import Fernet

import auth
import config
import database
import chat
import llm

logger = logging.getLogger(__name__)

_BASE_DIR = pathlib.Path(__file__).parent

_MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def _format_date(date_str: str) -> str:
    """Преобразовать YYYY-MM-DD в человекочитаемый формат: «24 марта 2026»."""
    try:
        d = datetime.date.fromisoformat(date_str)
        return f"{d.day} {_MONTHS_RU[d.month]} {d.year}"
    except (ValueError, KeyError):
        return date_str


def create_web_app() -> web.Application:
    """Создать и настроить aiohttp-приложение для веб-ленты."""
    app = web.Application()

    # Сессии (EncryptedCookieStorage на Fernet)
    fernet_key = Fernet(config.SESSION_SECRET_KEY.encode())
    setup_session(app, EncryptedCookieStorage(fernet_key))

    # Auth middleware (должен идти после session middleware, добавленного setup_session)
    app.middlewares.append(auth.auth_middleware)

    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(_BASE_DIR / "templates")),
    )

    app.router.add_get("/", handle_index)
    app.router.add_get("/auth/login", auth.handle_login_page)
    app.router.add_get("/auth/callback", auth.handle_auth_callback)
    app.router.add_post("/auth/logout", auth.handle_logout)
    app.router.add_get("/admin/stats", handle_admin_stats)
    app.router.add_get("/admin/prompt", handle_admin_prompt)
    app.router.add_post("/admin/prompt", handle_admin_prompt_save)
    app.router.add_post("/admin/prompt/reset", handle_admin_prompt_reset)
    app.router.add_get("/admin/prompt/history", handle_admin_prompt_history)
    app.router.add_get("/admin/chat/dialogs", handle_chat_dialogs_list)
    app.router.add_post("/admin/chat/dialogs", handle_chat_dialog_create)
    app.router.add_get("/admin/chat/dialogs/{dialog_id}/messages", handle_chat_messages_list)
    app.router.add_post("/admin/chat/dialogs/{dialog_id}/messages", handle_chat_message_send)
    app.router.add_static(
        "/static", path=str(_BASE_DIR / "static"), name="static",
    )

    return app


@aiohttp_jinja2.template("summaries.html")
async def handle_index(request: web.Request) -> dict:
    """Обработчик главной страницы: отдать последние 30 сводок."""
    summaries = await database.get_summaries_for_feed(limit=30)
    for s in summaries:
        s["date_display"] = _format_date(s["date"])
    return {
        "summaries": summaries,
        "user": request.get("user"),
        "bot_id": config.BOT_ID,
    }


def _get_default_prompt(prompt_key: str) -> str:
    """Вернуть дефолтный промпт для заданного ключа."""
    if prompt_key == "chat_system_prompt":
        return chat.DEFAULT_CHAT_PROMPT
    return llm.DEFAULT_SYSTEM_PROMPT


def _get_changed_by(user: dict) -> str:
    """Сформировать строку changed_by из данных сессии авторизации."""
    username = user.get("username")
    if username:
        return f"@{username}"
    return user.get("first_name", "admin")


async def handle_admin_stats(request: web.Request) -> web.Response:
    """Вернуть статистику для дашборда в JSON."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")
    stats = await database.get_stats()
    return web.Response(
        text=json.dumps(stats, ensure_ascii=False),
        content_type="application/json",
    )


async def handle_admin_prompt(request: web.Request) -> web.Response:
    """Вернуть текущий промпт и историю версий в JSON."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")

    prompt_key = request.rel_url.query.get("prompt_key", "system_prompt")
    stored = await database.get_setting(prompt_key)
    is_default = stored is None
    current_prompt = stored if stored is not None else _get_default_prompt(prompt_key)

    history_rows = await database.get_prompt_history(limit=20, prompt_key=prompt_key)
    history = []
    for row in history_rows:
        history.append({
            "id": row["id"],
            "prompt_text": row["prompt_text"],
            "changed_at": row["changed_at"],
            "changed_by": row["changed_by"],
            "preview": row["prompt_text"][:80],
        })

    data = {
        "current_prompt": current_prompt,
        "is_default": is_default,
        "history": history,
    }
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json",
    )


async def handle_admin_prompt_save(request: web.Request) -> web.Response:
    """Сохранить новый промпт в settings и записать старый в историю."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")

    body = await request.json()
    new_prompt = body.get("prompt_text", "").strip()
    if not new_prompt:
        raise web.HTTPBadRequest(text="prompt_text не может быть пустым")
    prompt_key = body.get("prompt_key", "system_prompt").strip() or "system_prompt"

    now = int(time.time())
    changed_by = _get_changed_by(user)

    # Сохраняем текущий промпт в историю перед заменой
    stored = await database.get_setting(prompt_key)
    old_prompt = stored if stored is not None else _get_default_prompt(prompt_key)
    await database.save_prompt_history(old_prompt, now, changed_by, prompt_key=prompt_key)

    await database.set_setting(prompt_key, new_prompt, now)
    logger.info("Промпт %s обновлён пользователем %s", prompt_key, changed_by)

    return web.Response(
        text=json.dumps({"status": "ok"}, ensure_ascii=False),
        content_type="application/json",
    )


async def handle_admin_prompt_reset(request: web.Request) -> web.Response:
    """Сбросить промпт к дефолту: удалить из settings, сохранить в историю."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")

    try:
        body = await request.json()
        prompt_key = body.get("prompt_key", "system_prompt").strip() or "system_prompt"
    except Exception:
        prompt_key = "system_prompt"

    now = int(time.time())
    changed_by = _get_changed_by(user)

    stored = await database.get_setting(prompt_key)
    if stored is not None:
        await database.save_prompt_history(stored, now, changed_by, prompt_key=prompt_key)
        await database.delete_setting(prompt_key)
        logger.info("Промпт %s сброшен к дефолту пользователем %s", prompt_key, changed_by)

    return web.Response(
        text=json.dumps({"status": "ok", "prompt": _get_default_prompt(prompt_key)}, ensure_ascii=False),
        content_type="application/json",
    )


async def handle_admin_prompt_history(request: web.Request) -> web.Response:
    """Вернуть историю версий промпта по ключу в JSON."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")
    prompt_key = request.rel_url.query.get("prompt_key", "system_prompt")
    rows = await database.get_prompt_history(limit=20, prompt_key=prompt_key)
    history = [
        {
            "id": r["id"],
            "prompt_text": r["prompt_text"],
            "changed_at": r["changed_at"],
            "changed_by": r["changed_by"],
            "preview": r["prompt_text"][:80],
        }
        for r in rows
    ]
    return web.Response(
        text=json.dumps(history, ensure_ascii=False),
        content_type="application/json",
    )


# ── Чат с Лешим ──────────────────────────────────────────────────────────────

async def _require_own_dialog(dialog_id: int, user_id: int) -> dict:
    """Вернуть диалог или поднять HTTPForbidden если не найден / не принадлежит пользователю."""
    dialog = await database.get_dialog(dialog_id)
    if dialog is None or dialog["user_id"] != user_id:
        raise web.HTTPForbidden(text="Диалог не найден")
    return dialog


async def handle_chat_dialogs_list(request: web.Request) -> web.Response:
    """Вернуть список диалогов текущего пользователя."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")
    user_id = int(user["id"])
    dialogs = await database.get_dialogs(user_id)
    data = [{"id": d["id"], "created_at": d["created_at"], "updated_at": d["updated_at"]} for d in dialogs]
    return web.Response(text=json.dumps(data, ensure_ascii=False), content_type="application/json")


async def handle_chat_dialog_create(request: web.Request) -> web.Response:
    """Создать новый диалог для текущего пользователя."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")
    user_id = int(user["id"])
    dialog_id = await database.create_dialog(user_id)
    return web.Response(
        text=json.dumps({"dialog_id": dialog_id}, ensure_ascii=False),
        content_type="application/json",
    )


async def handle_chat_messages_list(request: web.Request) -> web.Response:
    """Вернуть историю сообщений диалога (только user и assistant)."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")
    user_id = int(user["id"])
    dialog_id = int(request.match_info["dialog_id"])
    await _require_own_dialog(dialog_id, user_id)
    all_msgs = await database.get_all_dialog_messages(dialog_id)
    msgs = [
        {"role": m["role"], "content": m["content"], "created_at": m["created_at"]}
        for m in all_msgs
        if m["role"] in ("user", "assistant")
    ]
    return web.Response(text=json.dumps(msgs, ensure_ascii=False), content_type="application/json")


async def handle_chat_message_send(request: web.Request) -> web.Response:
    """Отправить сообщение в диалог, получить ответ Лешего."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")
    user_id = int(user["id"])
    dialog_id = int(request.match_info["dialog_id"])
    await _require_own_dialog(dialog_id, user_id)
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise web.HTTPBadRequest(text="message не может быть пустым")
    reply = await chat.chat_with_leshy(dialog_id, message)
    return web.Response(
        text=json.dumps({"reply": reply}, ensure_ascii=False),
        content_type="application/json",
    )
