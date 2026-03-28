"""Публичная веб-лента сводок TaigaBot Lite.

Предоставляет read-only веб-страницу с архивом сводок в обратном
хронологическом порядке. Каждая сводка отображается как карточка
с картинкой МЕМ ДНЯ (если есть) и текстом.

Авторизованные администраторы видят скелет дашборда над лентой.
"""

import datetime
import logging
import pathlib

import aiohttp_jinja2
import jinja2
from aiohttp import web
from aiohttp_session import setup as setup_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography.fernet import Fernet

import auth
import config
import database

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
