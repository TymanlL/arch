"""Точка входа: запускает Telegram-бота."""
import asyncio

from app.bot import main

if __name__ == "__main__":
    asyncio.run(main())
