"""Загрузка и валидация конфигурации из файла .env.

При импорте модуля переменные окружения читаются из .env (если файл существует),
затем валидируются. Если хотя бы одна обязательная переменная отсутствует или пуста —
модуль выбрасывает ValueError с указанием конкретной переменной.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Вернуть значение переменной окружения или выбросить ValueError."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Отсутствует обязательная переменная окружения: {name}")
    return value


def _parse_admin_ids() -> frozenset[int]:
    """Считать ADMIN_IDS из окружения, разбить по запятой, вернуть frozenset[int]."""
    raw = os.environ.get("ADMIN_IDS", "").strip()
    if not raw:
        raise ValueError("Отсутствует обязательная переменная окружения: ADMIN_IDS")
    return frozenset(int(x.strip()) for x in raw.split(",") if x.strip())


BOT_TOKEN: str = _require("BOT_TOKEN")
ALLOWED_CHAT_ID: int = int(_require("ALLOWED_CHAT_ID"))
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
OPENAI_MODEL: str = _require("OPENAI_MODEL")
SUMMARY_TIME: str = _require("SUMMARY_TIME")
TIMEZONE: str = _require("TIMEZONE")
ADMIN_IDS: frozenset[int] = _parse_admin_ids()

# Опциональные настройки генерации картинок (имеют defaults, бот работает без них)
IMAGE_MODEL: str = os.environ.get("IMAGE_MODEL", "gpt-image-1-mini").strip() or "gpt-image-1-mini"
IMAGE_QUALITY: str = os.environ.get("IMAGE_QUALITY", "low").strip() or "low"
IMAGE_SIZE: str = os.environ.get("IMAGE_SIZE", "1024x1024").strip() or "1024x1024"
