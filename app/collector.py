"""Сбор постов из Telegram-канала через userbot (Telethon)."""
from app import config


def _post_from_msg(msg, entity):
    text = (msg.message or "").strip()
    if not text:
        return None
    username = getattr(entity, "username", None)
    url = f"https://t.me/{username}/{msg.id}" if username else ""
    return {
        "tg_message_id": msg.id,
        "text": text,
        "url": url,
        "date": msg.date.isoformat() if msg.date else "",
    }


async def collect_posts(user_client, entity, last_message_id):
    """Возвращает список новых постов (старые -> новые).

    Если канал ещё не разбирали (last_message_id == 0) — берём последние
    INITIAL_FETCH_LIMIT постов. Иначе — только то, что новее last_message_id.
    """
    posts = []
    if last_message_id and last_message_id > 0:
        async for msg in user_client.iter_messages(
            entity, min_id=last_message_id, reverse=True
        ):
            post = _post_from_msg(msg, entity)
            if post:
                posts.append(post)
    else:
        recent = []
        async for msg in user_client.iter_messages(
            entity, limit=config.INITIAL_FETCH_LIMIT
        ):
            recent.append(msg)
        for msg in reversed(recent):  # iter_messages отдаёт новые -> старые
            post = _post_from_msg(msg, entity)
            if post:
                posts.append(post)
    return posts
