import asyncio
import time
from aiogram import Bot
import config, database, worker

async def main():
    await database.init_db()
    
    # Вставляем 12 тестовых сообщений прямо в базу
    # минуя Telegram — для теста это абсолютно нормально
    now = int(time.time())
    test_messages = [
        ("user1", "Привет всем, как дела?"),
        ("user2", "Нормально, работаем"),
        ("user1", "Кто смотрел новый релиз?"),
        ("user3", "Я смотрел, интересно"),
        ("user2", "Там много чего нового"),
        ("user4", "Надо разобраться с деплоем"),
        ("user1", "Давайте завтра созвонимся"),
        ("user3", "Я за, во сколько?"),
        ("user4", "В 11 удобно?"),
        ("user2", "Мне тоже подходит"),
        ("user1", "Договорились"),
        ("user3", "Отлично, жду"),
    ]
    for username, text in test_messages:
        await database.save_message(
            user_id=f"test_{username}",
            username=username,
            text=text,
            timestamp=now - 3600,  # час назад
        )
    
    print("Тестовые сообщения добавлены в базу")
    
    bot = Bot(token=config.BOT_TOKEN)
    await worker.run_daily_summary(bot)
    await bot.session.close()
    
    print("Проверяем summaries:")
    import sqlite3
    conn = sqlite3.connect("taigabot.db")
    rows = conn.execute("SELECT date, summary_text FROM summaries").fetchall()
    for row in rows:
        print(f"Дата: {row[0]}\n{row[1]}")

asyncio.run(main())
