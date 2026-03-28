"""Авторизация через Telegram Login и управление сессиями.

Используется стандартный Telegram Login Widget в режиме redirect (data-auth-url).
Telegram перенаправляет браузер на /auth/callback с данными в query-параметрах.
Валидация через HMAC-SHA256 (legacy hash flow).

JWT-валидация через JWKS сохранена для возможного использования в будущем.

Middleware загружает данные пользователя из сессии в request['user'].
"""

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any

import aiohttp_jinja2
import jwt
from jwt import PyJWKClient
from aiohttp import web
from aiohttp_session import get_session

import config

logger = logging.getLogger(__name__)

# --- JWKS-клиент (синглтон, кеширует ключи автоматически) ---

TELEGRAM_JWKS_URL = "https://oauth.telegram.org/.well-known/jwks.json"
TELEGRAM_ISSUER = "https://oauth.telegram.org"

_jwks_client = PyJWKClient(TELEGRAM_JWKS_URL)


# --- Валидация JWT (новый flow, сохранена для будущего использования) ---

async def _validate_jwt(id_token: str) -> dict[str, Any]:
    """Валидировать JWT id_token от Telegram Login.

    PyJWKClient.get_signing_key_from_jwt() — синхронный метод (HTTP-запрос
    к JWKS endpoint), поэтому вызываем через asyncio.to_thread().

    Возвращает нормализованный словарь {id, first_name, username}.
    """
    signing_key = await asyncio.to_thread(
        _jwks_client.get_signing_key_from_jwt, id_token
    )
    payload = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=TELEGRAM_ISSUER,
        audience=str(config.BOT_ID),
    )
    return {
        "id": payload.get("sub") or payload.get("id"),
        "first_name": payload.get("name", ""),
        "username": payload.get("preferred_username", ""),
    }


# --- Валидация legacy hash ---

def _validate_legacy_hash(data: dict[str, Any]) -> dict[str, Any]:
    """Валидировать hash-based данные по протоколу Telegram Login Widget.

    Алгоритм: https://core.telegram.org/widgets/login#checking-authorization
    1. data-check-string: все поля кроме hash, отсортированные, key=value через \\n
    2. secret_key = SHA256(bot_token)
    3. Сравнить HMAC-SHA256(secret_key, data-check-string) с hash
    4. Проверить auth_date не старше 86400 секунд (1 день)

    Возвращает нормализованный словарь {id, first_name, username}.
    Выбрасывает ValueError при невалидных данных.
    """
    received_hash = data.get("hash", "")

    # Собираем data-check-string (все поля кроме hash)
    check_fields = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(check_fields.items())
    )

    # secret_key = SHA256(bot_token)
    secret_key = hashlib.sha256(config.BOT_TOKEN.encode()).digest()

    # HMAC-SHA256
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Невалидная подпись данных")

    # Проверка свежести (не старше 1 дня)
    auth_date = int(data.get("auth_date", 0))
    if time.time() - auth_date > 86400:
        raise ValueError("Данные авторизации устарели")

    return {
        "id": data["id"],
        "first_name": data.get("first_name", ""),
        "username": data.get("username", ""),
    }


# --- Middleware ---

@web.middleware
async def auth_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    """Загрузить данные пользователя из сессии в request['user']."""
    session = await get_session(request)
    if "user_id" in session:
        request["user"] = {
            "id": session["user_id"],
            "first_name": session.get("first_name", ""),
            "username": session.get("username", ""),
        }
    else:
        request["user"] = None
    return await handler(request)


# --- Хэндлеры ---

async def handle_login_page(request: web.Request) -> web.Response:
    """GET /auth/login — страница с кнопкой Telegram Login Widget."""
    return aiohttp_jinja2.render_template("login.html", request, {
        "bot_username": config.BOT_USERNAME,
        "auth_callback_url": "https://taiga.ex-mari.com/auth/callback",
    })


async def handle_auth_callback(request: web.Request) -> web.Response:
    """GET /auth/callback — Telegram редиректит сюда с данными в query params.

    Параметры: id, first_name, last_name, username, photo_url, auth_date, hash.
    Валидация через HMAC-SHA256.
    """
    data = dict(request.query)

    if "hash" not in data:
        return web.Response(text="Отсутствуют данные авторизации", status=400)

    try:
        user_info = _validate_legacy_hash(data)
    except Exception:
        logger.warning("Auth validation failed", exc_info=True)
        return web.Response(
            text="Авторизация не удалась",
            status=403,
            content_type="text/plain; charset=utf-8",
        )

    user_id = int(user_info["id"])
    if user_id not in config.ADMIN_IDS:
        return web.Response(
            text="Лес закрыт. Ты не из моего леса.",
            status=403,
            content_type="text/plain; charset=utf-8",
        )

    # Создание сессии
    session = await get_session(request)
    session["user_id"] = user_id
    session["first_name"] = user_info.get("first_name", "")
    session["username"] = user_info.get("username", "")

    logger.info("Админ авторизован: %s (id=%d)", user_info.get("first_name"), user_id)

    # Redirect на главную — пользователь увидит дашборд
    raise web.HTTPFound("/")


async def handle_logout(request: web.Request) -> web.Response:
    """POST /auth/logout — очистить сессию."""
    session = await get_session(request)
    session.invalidate()
    return web.json_response({"ok": True})
