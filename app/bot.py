"""Telegram-бот: интерфейс + оркестрация конвейера (Telegram + YouTube)."""
import asyncio
import re

from telethon import TelegramClient, events

from app import config, db, youtube
from app.collector import collect_posts
from app.extractor import extract_items
from app.markdown_export import export_channel
from app.prompts import CATEGORY_TITLES

HELP_TEXT = (
    "Привет! Я разбираю публичные каналы на полезные знания.\n\n"
    "Пришли мне ссылку:\n"
    "• Telegram-канал: `https://t.me/friendshipwithbrain`\n"
    "• YouTube-канал: `https://youtube.com/@channel`\n\n"
    "Я заберу посты/видео, вытащу факты, ссылки на исследования, техники и "
    "лайфхаки, сохраню в память и пришлю Markdown-файлы.\n\n"
    "По умолчанию беру свежие записи (быстро). Чтобы выкачать **весь архив** — "
    "команда `/full <ссылка>`.\n\n"
    "Команды:\n"
    "• `/full <ссылка>` — выкачать весь архив канала целиком\n"
    "• `/list` — какие каналы уже разобраны\n"
    "• `/digest <канал>` — прислать выжимку по каналу заново\n"
    "• `/search <слово>` — поиск по всей накопленной базе"
)


def _is_allowed(event) -> bool:
    return not config.ALLOWED_USER_IDS or event.sender_id in config.ALLOWED_USER_IDS


def detect_platform(text: str) -> str:
    t = (text or "").lower()
    if "youtube.com" in t or "youtu.be" in t:
        return "youtube"
    return "telegram"


def parse_channel_ref(text: str):
    """Из telegram-ссылки/упоминания достаёт username канала или None."""
    text = (text or "").strip()
    text = re.sub(r"^https?://", "", text)
    if text.startswith("t.me/"):
        text = text[len("t.me/") :]
    text = text.lstrip("@")
    text = text.split("/")[0].split("?")[0]
    return text if re.fullmatch(r"[A-Za-z0-9_]{4,}", text) else None


def _format_summary(title, n_units, unit, counts) -> str:
    if not counts:
        return f"✅ «{title}»: обработал {n_units} {unit}, но полезных пунктов не нашлось."
    lines = [f"✅ «{title}»: обработал {n_units} {unit}.\n"]
    for cat, ctitle in CATEGORY_TITLES.items():
        if counts.get(cat):
            lines.append(f"• {ctitle}: {counts[cat]}")
    return "\n".join(lines)


async def _finish(event, status, channel_id, username, title, posts, unit, batch_size):
    """Общая стадия: сохранить, извлечь, разложить, экспортировать, ответить."""
    if not posts:
        await status.edit(f"✅ «{title}»: новых записей нет, всё уже разобрано.")
        return

    await status.edit(f"📥 Собрал {len(posts)} {unit} из «{title}». Извлекаю знания…")
    for post in posts:
        db.insert_post(channel_id, post)

    extracted = await extract_items(posts, batch_size=batch_size)
    counts = {}
    for item in extracted:
        category = item["category"]
        content = item["content"]
        if category not in CATEGORY_TITLES or not content:
            continue
        post = item["post"]
        source_url = item.get("link") or post.get("url", "")
        if db.insert_item(
            channel_id, post["ext_post_id"], category, content, source_url, post.get("date", "")
        ):
            counts[category] = counts.get(category, 0) + 1

    files = export_channel(channel_id, username, title)
    await status.edit(_format_summary(title, len(posts), unit, counts))
    for path in files:
        await event.client.send_file(event.chat_id, path)


async def _process_telegram(event, user_client, ref, full=False):
    status = await event.respond(f"🔍 Открываю Telegram-канал @{ref}…")
    try:
        entity = await user_client.get_entity(ref)
    except Exception as exc:  # noqa: BLE001
        await status.edit(f"❌ Не смог открыть @{ref}: {exc}")
        return

    title = getattr(entity, "title", ref)
    username = getattr(entity, "username", ref)
    channel_id, last_id = db.get_or_create_channel("telegram", entity.id, username, title)

    if full:
        await status.edit(f"📚 Выкачиваю весь архив «{title}» — это может занять время…")
        known = db.existing_post_ids(channel_id)
        posts = await collect_posts(user_client, entity, last_id, full=True, known_ids=known)
    else:
        posts = await collect_posts(user_client, entity, last_id)

    if posts:
        new_last_id = max(int(p["ext_post_id"]) for p in posts)
        db.update_last_message_id(channel_id, new_last_id)

    await _finish(event, status, channel_id, username, title, posts, "постов", batch_size=None)


async def _process_youtube(event, url, full=False):
    status = await event.respond("🔍 Открываю YouTube-канал…")
    try:
        # резолвим канал и забираем известные id за один проход
        ext_id, username, title, _ = await asyncio.to_thread(
            youtube.collect_videos, url, 1, frozenset()
        )
    except Exception as exc:  # noqa: BLE001
        await status.edit(f"❌ Не смог открыть YouTube-канал: {exc}")
        return

    channel_id, _ = db.get_or_create_channel("youtube", ext_id, username, title)
    known = db.existing_post_ids(channel_id)
    limit = None if full else config.INITIAL_FETCH_LIMIT

    if full:
        await status.edit(f"📚 Выкачиваю весь архив «{title}» — расшифровка видео займёт время…")
    else:
        await status.edit(f"📥 Беру свежие видео «{title}» и расшифровываю…")

    try:
        _, _, title, posts = await asyncio.to_thread(
            youtube.collect_videos, url, limit, known
        )
    except Exception as exc:  # noqa: BLE001
        await status.edit(f"❌ Ошибка при сборе видео: {exc}")
        return

    await _finish(event, status, channel_id, username, title, posts, "видео", batch_size=1)


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
            for _cid, platform, username, title, n in channels:
                icon = "▶️" if platform == "youtube" else "✈️"
                lines.append(f"{icon} «{title}» (@{username}) — {n} пунктов")
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
            ctitle = CATEGORY_TITLES.get(category, category)
            src = f" — [источник]({url})" if url else ""
            lines.append(f"• [{ctitle} · @{username}] {content}{src}")
        await event.respond("\n".join(lines), link_preview=False)
        raise events.StopPropagation

    @bot.on(events.NewMessage(pattern=r"^/full(?:\s+(.+))?"))
    async def _full(event):
        if not _is_allowed(event):
            raise events.StopPropagation
        arg = (event.pattern_match.group(1) or "").strip()
        if not arg:
            await event.respond("Использование: `/full <ссылка на канал>`")
            raise events.StopPropagation
        if detect_platform(arg) == "youtube":
            await _process_youtube(event, arg, full=True)
        else:
            ref = parse_channel_ref(arg)
            if not ref:
                await event.respond("Не понял ссылку. Пример: `/full https://t.me/имя`")
            else:
                await _process_telegram(event, user_client, ref, full=True)
        raise events.StopPropagation

    @bot.on(events.NewMessage(pattern=r"^/digest(?:\s+(.+))?"))
    async def _digest(event):
        if not _is_allowed(event):
            raise events.StopPropagation
        arg = event.pattern_match.group(1) or ""
        ref = parse_channel_ref(arg)
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
        text = (event.raw_text or "").strip()
        if text.startswith("/"):
            return  # команды обрабатываются выше
        if detect_platform(text) == "youtube":
            await _process_youtube(event, text)
            return
        ref = parse_channel_ref(text)
        if not ref:
            await event.respond(
                "Не понял. Пришли ссылку на Telegram- или YouTube-канал, например "
                "`https://t.me/friendshipwithbrain`"
            )
            return
        await _process_telegram(event, user_client, ref)


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
