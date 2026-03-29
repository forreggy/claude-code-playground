"""Модуль интерактивного чата с Лешим (TLL-06).

Использует OpenAI-совместимый Chat Completions API через провайдер-агностичный клиент.
Провайдер задаётся через CHAT_API_BASE / CHAT_API_KEY / CHAT_MODEL в .env.
Поддерживаемые провайдеры: Cerebras, OpenRouter, Groq (любой с OpenAI-совместимым API и tool calling).

Это ДРУГОЙ клиент и ДРУГОЙ API, чем в llm.py:
  - llm.py:  OpenAI Responses API (client.responses.create), store=False, для сводок
  - chat.py: Chat Completions API (client.chat.completions.create), для интерактивного чата
"""

import asyncio
import json
import logging

from openai import AsyncOpenAI

import config

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(
    base_url=config.CHAT_API_BASE,
    api_key=config.CHAT_API_KEY,
)

# Сколько последних сообщений (user+assistant) отправлять модели
CONTEXT_WINDOW = 8

DEFAULT_CHAT_PROMPT = (
    "Ты — Леший. Цифровой дух тайги, мемолог, летописец и советник.\n\n"
    "В сводках ты молча наблюдаешь за чатом и потом выходишь с итогами. "
    "Здесь другое — тебя позвали поговорить лично. Ты отвечаешь на вопросы, "
    "помогаешь думать, подкидываешь идеи. Но характер тот же: ты не вежливый "
    "ассистент, ты — тот, кто видел всё из чащи и говорит как есть.\n\n"
    "Правила:\n\n"
    "Разговорный русский язык. Можно подколоть, нельзя унижать. "
    "Никакой канцелярщины и корпоративной вежливости.\n\n"
    "Если тебя спрашивают о чём-то, что требует свежих данных — "
    "используй инструмент web_search. Не выдумывай факты. "
    "Если не знаешь и поиск не помог — скажи честно.\n\n"
    "Если вопрос про маркетинг, контент, стратегию — отвечай по делу, "
    "с примерами и конкретикой. Ты не теоретик, ты практик из тайги.\n\n"
    "Отвечай компактно. Не лей воду. Если ответ — одно предложение, "
    "пусть будет одно предложение.\n\n"
    "Не начинай каждый ответ с обращения или приветствия. "
    "Не повторяй вопрос собеседника. Просто отвечай.\n\n"
    "Форматирование: HTML-теги для Telegram (<b>, <i>, <code>). Никакого Markdown."
)

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Поиск актуальной информации в интернете. "
            "Используй когда нужны свежие данные, новости, факты, цены, события."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Поисковый запрос на языке, наиболее подходящем для поиска "
                        "(русский или английский)"
                    ),
                }
            },
            "required": ["query"],
        },
    },
}


async def get_chat_prompt() -> str:
    """Читает chat_system_prompt из settings, fallback на DEFAULT_CHAT_PROMPT."""
    from database import get_setting
    custom = await get_setting("chat_system_prompt")
    return custom if custom else DEFAULT_CHAT_PROMPT


def execute_web_search(query: str, max_results: int = 5) -> str:
    """Выполняет поиск через DuckDuckGo, возвращает результаты как текст.

    Синхронная функция — вызывать из async-кода через asyncio.to_thread().
    """
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=max_results)
        if not results:
            return "Поиск не дал результатов."
        formatted = []
        for r in results:
            formatted.append(
                f"Заголовок: {r['title']}\nURL: {r['href']}\nОписание: {r['body']}"
            )
        return "\n\n---\n\n".join(formatted)
    except Exception as e:
        logger.error("Ошибка веб-поиска по запросу %r: %s", query, e)
        return f"Ошибка поиска: {e}"


async def chat_with_leshy(dialog_id: int, user_message: str) -> str:
    """Основная функция чата с Лешим.

    Алгоритм:
    1. Записывает user_message в dialog_messages.
    2. Достаёт последние CONTEXT_WINDOW сообщений (user+assistant) из БД.
    3. Собирает контекст: system prompt + сообщения.
    4. Отправляет в модель с инструментом web_search.
    5. Если модель вернула tool_calls — выполняет поиск, отправляет результат обратно.
       Максимум 3 итерации агентного цикла.
    6. Записывает финальный ответ в dialog_messages.
    7. Обновляет updated_at диалога.
    8. Возвращает текст ответа.
    """
    from database import (
        add_dialog_message,
        get_dialog_messages,
        update_dialog_timestamp,
    )

    # 1. Записываем сообщение пользователя
    await add_dialog_message(dialog_id, "user", user_message)

    # 2. Достаём последние сообщения для контекста
    recent = await get_dialog_messages(dialog_id, limit=CONTEXT_WINDOW)

    # 3. Собираем messages для API
    system_prompt = await get_chat_prompt()
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for msg in recent:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # 4. Первый вызов модели
    response = await _client.chat.completions.create(
        model=config.CHAT_MODEL,
        messages=messages,
        tools=[WEB_SEARCH_TOOL],
        tool_choice="auto",
    )
    assistant_message = response.choices[0].message

    # 5. Агентный цикл: обработка tool_calls (максимум 3 итерации)
    iterations = 0
    while assistant_message.tool_calls and iterations < 3:
        iterations += 1
        logger.info(
            "dialog_id=%d: tool_calls итерация %d, вызовов: %d",
            dialog_id,
            iterations,
            len(assistant_message.tool_calls),
        )

        # Добавляем ответ модели (с tool_calls) в контекст
        # content or "" — ряд провайдеров (Cerebras и др.) не принимают None в content
        messages.append({
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [tc.model_dump() for tc in assistant_message.tool_calls],
        })

        # Выполняем каждый tool call
        for tool_call in assistant_message.tool_calls:
            if tool_call.function.name == "web_search":
                args = json.loads(tool_call.function.arguments)
                query = args.get("query", "")
                logger.info("dialog_id=%d: web_search запрос: %r", dialog_id, query)
                search_result = await asyncio.to_thread(execute_web_search, query)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": search_result,
                })

        # Повторный вызов модели с результатами поиска
        response = await _client.chat.completions.create(
            model=config.CHAT_MODEL,
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="auto",
        )
        assistant_message = response.choices[0].message

    # 6. Извлекаем финальный текст
    reply_text = assistant_message.content or "Леший молчит. Попробуй ещё раз."

    # 7. Записываем ответ в БД и обновляем timestamp диалога
    await add_dialog_message(dialog_id, "assistant", reply_text)
    await update_dialog_timestamp(dialog_id)

    logger.info(
        "dialog_id=%d: ответ сформирован, итераций поиска: %d, длина: %d символов",
        dialog_id,
        iterations,
        len(reply_text),
    )
    return reply_text
