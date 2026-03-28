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

    stored = await database.get_setting("system_prompt")
    is_default = stored is None
    current_prompt = stored if stored is not None else llm.DEFAULT_SYSTEM_PROMPT

    history_rows = await database.get_prompt_history(limit=20)
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

    now = int(time.time())
    changed_by = _get_changed_by(user)

    # Сохраняем текущий промпт в историю перед заменой
    stored = await database.get_setting("system_prompt")
    old_prompt = stored if stored is not None else llm.DEFAULT_SYSTEM_PROMPT
    await database.save_prompt_history(old_prompt, now, changed_by)

    await database.set_setting("system_prompt", new_prompt, now)
    logger.info("Промпт обновлён пользователем %s", changed_by)

    return web.Response(
        text=json.dumps({"status": "ok"}, ensure_ascii=False),
        content_type="application/json",
    )


async def handle_admin_prompt_reset(request: web.Request) -> web.Response:
    """Сбросить промпт к дефолту: удалить из settings, сохранить в историю."""
    user = request.get("user")
    if not user:
        raise web.HTTPForbidden(text="Доступ запрещён")

    now = int(time.time())
    changed_by = _get_changed_by(user)

    stored = await database.get_setting("system_prompt")
    if stored is not None:
        await database.save_prompt_history(stored, now, changed_by)
        await database.delete_setting("system_prompt")
        logger.info("Промпт сброшен к дефолту пользователем %s", changed_by)

    return web.Response(
        text=json.dumps({"status": "ok", "prompt": llm.DEFAULT_SYSTEM_PROMPT}, ensure_ascii=False),
        content_type="application/json",
    )
