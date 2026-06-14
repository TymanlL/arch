"""Сбор видео YouTube-канала: список через yt-dlp + субтитры (расшифровка).

Функции синхронные (yt-dlp и youtube-transcript-api блокирующие) — в боте они
вызываются через asyncio.to_thread, чтобы не блокировать event loop.
"""
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi


def _videos_url(channel_url: str) -> str:
    """Нормализует ссылку на канал к вкладке /videos."""
    url = channel_url.strip().rstrip("/")
    if "youtu.be/" in url or "watch?v=" in url:
        return url  # одиночное видео — оставляем как есть
    if "/videos" in url or "/playlist" in url:
        return url
    return url + "/videos"


def _fetch_transcript(video_id: str) -> str:
    """Возвращает текст субтитров (ru/en в приоритете, иначе любые) или ''."""
    try:
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=["ru", "en"])
        return " ".join(s["text"] for s in segs).strip()
    except Exception:
        pass
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        first = next(iter(transcripts))
        return " ".join(s["text"] for s in first.fetch()).strip()
    except Exception:
        return ""


def collect_videos(channel_url, limit=None, known_ids=frozenset()):
    """Возвращает (channel_id, username, title, posts).

    posts (старые -> новые) содержат расшифровки видео, ещё не сохранённых.
    limit ограничивает число просматриваемых последних видео (None — все).
    """
    opts = {
        "extract_flat": True,
        "quiet": True,
        "skip_download": True,
        "ignoreerrors": True,
    }
    if limit:
        opts["playlistend"] = limit

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(_videos_url(channel_url), download=False)

    if not info:
        raise RuntimeError("yt-dlp не смог открыть канал")

    channel_id = info.get("channel_id") or info.get("uploader_id") or info.get("id")
    title = info.get("channel") or info.get("uploader") or info.get("title") or channel_id
    username = info.get("uploader_id") or info.get("channel_id") or channel_id

    entries = [e for e in (info.get("entries") or []) if e]
    posts = []
    for entry in entries:
        vid = entry.get("id")
        if not vid or vid in known_ids:
            continue
        text = _fetch_transcript(vid)
        if not text:
            continue  # без субтитров пока пропускаем (Whisper — следующий этап)
        posts.append(
            {
                "ext_post_id": vid,
                "text": text,
                "url": f"https://youtu.be/{vid}",
                "date": "",  # flat-список не отдаёт дату; не критично для выжимки
                "title": entry.get("title"),
            }
        )
    posts.reverse()  # entries новые -> старые, приводим к старые -> новые
    return channel_id, username, title, posts
