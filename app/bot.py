"""Telegram-бот: интерфейс + оркестрация конвейера."""
import asyncio
import re

from telethon import TelegramClient, events

from app import config, db
from app.collector import collect_posts
from app.extractor import extract_items
from app.markdown_export import export_channel
from app.prompts import CATEGORY_TITLES

HELP_TEXT = (
    "Привет! Я разбираю публичные Telegram-каналы на полезные знания.\n\n"
    "Просто пришли мне ссылку на канал, например:\n"
    "`https://t.me/friendshipwithbrain`\n\n"
    "Я заберу посты, вытащу факты, ссылки на исследования, техники и лайфхаки, "
    "сохраню в память и пришлю Markdown-файлы.\n\n"
    "Команды:\n"
    "• `/list` — какие каналы уже разобраны\n"
    "• `/digest <канал>` — прислать выжимку по каналу заново\n"
    "• `/search <слово>` — поиск по всей накопленной базе"
)


def _is_allowed(event) -> bool:
    return not config.ALLOWED_USER_IDS or event.sender_id in config.ALLOWED_USER_IDS


def parse_channel_ref(text: str):
    """Из ссылки/упоминания достаёт username канала или None."""
    text = (text or "").strip()
    text = re.sub(r"^https?://", "", text)
    if text.startswith("t.me/"):
        text = text[len("t.me/") :]
    text = text.lstrip("@")
    text = text.split("/")[0].split("?")[0]
    return text if re.fullmatch(r"[A-Za-z0-9_]{4,}", text) else None


def _format_summary(channel_title, n_posts, counts) -> str:
    if not counts:
        return (
            f"✅ Канал «{channel_title}»: обработал {n_posts} постов, "
            "но полезных пунктов не нашлось."
        )
    lines = [f"✅ Канал «{channel_title}»: обработал {n_posts} постов.\n"]
    for cat, title in CATEGORY_TITLES.items():
        if counts.get(cat):
            lines.append(f"• {title}: {counts[cat]}")
    return "\n".join(lines)


async def _process(event, user_client, ref):
    status = await event.respond(f"🔍 Открываю канал @{ref}…")
    try:
        entity = await user_client.get_entity(ref)
    except Exception as exc:  # noqa: BLE001
        await status.edit(f"❌ Не смог открыть @{ref}: {exc}")
        return

    title = getattr(entity, "title", ref)
    username = getattr(entity, "username", ref)
    channel_id, last_id = db.get_or_create_channel(entity.id, username, title)

    posts = await collect_posts(user_client, entity, last_id)
    if not posts:
        await status.edit(f"✅ «{title}»: новых постов нет, всё уже разобрано.")
        return

    await status.edit(f"📥 Собрал {len(posts)} постов из «{title}». Извлекаю знания…")
    for post in posts:
        db.insert_post(channel_id, post)

    raw_items = await extract_items(posts)

    post_by_id = {p["tg_message_id"]: p for p in posts}
    counts = {}
    for item in raw_items:
        category = item.get("category")
        content = (item.get("content") or "").strip()
        if category not in CATEGORY_TITLES or not content:
            continue
        post = post_by_id.get(item.get("post_id"))
        source_url = item.get("link") or (post["url"] if post else "")
        date = post["date"] if post else ""
        if db.insert_item(
            channel_id, item.get("post_id"), category, content, source_url, date
        ):
            counts[category] = counts.get(category, 0) + 1

    new_last_id = max(p["tg_message_id"] for p in posts)
    db.update_last_message_id(channel_id, new_last_id)

    files = export_channel(channel_id, username, title)
    await status.edit(_format_summary(title, len(posts), counts))
    for path in files:
        await event.client.send_file(event.chat_id, path)


def register_handlers(bot: TelegramClient, user_client: TelegramClient) -> None:
    @bot.on(events.NewMessage(pattern=r"^/(start|help)"))
    async def _help(event):
        if not _is_allowed(event):
            raise events.StopPropagation
        await event.respond(HELP_TEXT)
        raise events.StopPropagation

    @bot.on(events.NewMessage(pattern=r"^/list"))
    async def _list(event):
        if not _is_allowed(event):
            raise events.StopPropagation
        channels = db.list_channels()
        if not channels:
            await event.respond("Пока ничего не разобрано. Пришли ссылку на канал.")
        else:
            lines = ["📚 Разобранные каналы:\n"]
            for _cid, username, title, n in channels:
                lines.append(f"• «{title}» (@{username}) — {n} пунктов")
            await event.respond("\n".join(lines))
        raise events.StopPropagation

    @bot.on(events.NewMessage(pattern=r"^/search(?:\s+(.+))?"))
    async def _search(event):
        if not _is_allowed(event):
            raise events.StopPropagation
        query = (event.pattern_match.group(1) or "").strip()
        if not query:
            await event.respond("Использование: `/search слово`")
            raise events.StopPropagation
        results = db.search_items(query)
        if not results:
            await event.respond(f"По запросу «{query}» ничего не нашёл.")
            raise events.StopPropagation
        lines = [f"🔎 Результаты по «{query}»:\n"]
        for category, content, url, username in results:
            title = CATEGORY_TITLES.get(category, category)
            src = f" — [источник]({url})" if url else ""
            lines.append(f"• [{title} · @{username}] {content}{src}")
        await event.respond("\n".join(lines), link_preview=False)
        raise events.StopPropagation

    @bot.on(events.NewMessage(pattern=r"^/digest(?:\s+(.+))?"))
    async def _digest(event):
        if not _is_allowed(event):
            raise events.StopPropagation
        ref = parse_channel_ref(event.pattern_match.group(1) or "")
        if not ref:
            await event.respond("Использование: `/digest имя_канала`")
            raise events.StopPropagation
        found = db.get_channel_by_username(ref)
        if not found:
            await event.respond(f"Канал @{ref} ещё не разбирали. Пришли ссылку на него.")
            raise events.StopPropagation
        channel_id, username, title = found
        files = export_channel(channel_id, username, title)
        if not files:
            await event.respond(f"По «{title}» пока нет сохранённых пунктов.")
            raise events.StopPropagation
        await event.respond(f"📄 Выжимка по «{title}»:")
        for path in files:
            await event.client.send_file(event.chat_id, path)
        raise events.StopPropagation

    @bot.on(events.NewMessage)
    async def _default(event):
        if not _is_allowed(event):
            return
        text = event.raw_text or ""
        if text.startswith("/"):
            return  # команды обрабатываются выше
        ref = parse_channel_ref(text)
        if not ref:
            await event.respond(
                "Не понял. Пришли ссылку на канал, например "
                "`https://t.me/friendshipwithbrain`"
            )
            return
        await _process(event, user_client, ref)


async def main() -> None:
    config.validate()
    db.init_db()

    user_client = TelegramClient(config.USERBOT_SESSION, config.TG_API_ID, config.TG_API_HASH)
    await user_client.connect()
    if not await user_client.is_user_authorized():
        raise RuntimeError(
            "Userbot не авторизован. Сначала выполни один раз: python login.py"
        )

    bot = TelegramClient(config.BOT_SESSION, config.TG_API_ID, config.TG_API_HASH)
    await bot.start(bot_token=config.TG_BOT_TOKEN)

    register_handlers(bot, user_client)
    me = await bot.get_me()
    print(f"Бот запущен: @{me.username}. Жду сообщения…")

    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot.run_until_disconnected(),
    )
