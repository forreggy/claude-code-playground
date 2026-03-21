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


BOT_TOKEN: str = _require("BOT_TOKEN")
ALLOWED_CHAT_ID: int = int(_require("ALLOWED_CHAT_ID"))
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
OPENAI_MODEL: str = _require("OPENAI_MODEL")
SUMMARY_TIME: str = _require("SUMMARY_TIME")
TIMEZONE: str = _require("TIMEZONE")
