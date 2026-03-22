import asyncio
import llm

messages = [
    {"username": "alexey_dev", "text": "Почему у нас в проде опять падает celery?"},
    {"username": "marina_qa", "text": "Потому что никто не читает логи. Там же всё написано"},
    {"username": "dmitry_pm", "text": "Давайте поставим задачу на следующий спринт"},
    {"username": "alexey_dev", "text": "Какой спринт, прод горит!"},
    {"username": None, "text": "Может просто перезапустить?"},
    {"username": "marina_qa", "text": "Перезапуск не поможет, там утечка памяти"},
    {"username": "dmitry_pm", "text": "Окей, ставлю приоритет высокий"},
]

result = asyncio.run(llm.generate_summary(messages))
print(result)
