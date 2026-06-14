"""Одноразовый вход userbot'а: создаёт session-файл для чтения каналов.

Запусти ОДИН раз на VPS:  python login.py
Тебя спросят номер телефона и код из Telegram (и пароль 2FA, если включён).
После этого main.py сможет читать каналы без интерактива.
"""
import asyncio

from telethon import TelegramClient

from app import config


async def main() -> None:
    config.validate()
    client = TelegramClient(
        config.USERBOT_SESSION, config.TG_API_ID, config.TG_API_HASH
    )
    await client.start()  # интерактивно спросит телефон + код
    me = await client.get_me()
    print(f"Готово. Userbot авторизован как: {me.username or me.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
