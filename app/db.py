"""SQLite-хранилище: каналы, посты/видео, извлечённые пункты («память»).

Схема обобщена под несколько платформ (telegram, youtube, …):
- channels.platform + channels.ext_id однозначно идентифицируют источник;
- posts.ext_post_id — id поста (telegram) или видео (youtube), строкой.
"""
import datetime
import os
import sqlite3

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT,
    ext_id          TEXT,
    username        TEXT,
    title           TEXT,
    last_message_id INTEGER DEFAULT 0,
    added_at        TEXT,
    UNIQUE(platform, ext_id)
);
CREATE TABLE IF NOT EXISTS posts(
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   INTEGER,
    ext_post_id  TEXT,
    date         TEXT,
    text         TEXT,
    url          TEXT,
    title        TEXT,
    UNIQUE(channel_id, ext_post_id)
);
CREATE TABLE IF NOT EXISTS items(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  INTEGER,
    post_ext_id TEXT,
    category    TEXT,
    content     TEXT,
    source_url  TEXT,
    date        TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_channel ON items(channel_id, category);
"""


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(SCHEMA)


def get_or_create_channel(platform, ext_id, username, title):
    """Возвращает (channel_id, last_message_id)."""
    ext_id = str(ext_id)
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, last_message_id FROM channels WHERE platform=? AND ext_id=?",
            (platform, ext_id),
        ).fetchone()
        if row:
            return row["id"], row["last_message_id"] or 0
        cur = conn.execute(
            "INSERT INTO channels(platform, ext_id, username, title, last_message_id, "
            "added_at) VALUES(?,?,?,?,0,?)",
            (platform, ext_id, username, title, datetime.datetime.utcnow().isoformat()),
        )
        return cur.lastrowid, 0


def update_last_message_id(channel_id, last_id) -> None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT last_message_id FROM channels WHERE id=?", (channel_id,)
        ).fetchone()
        existing = (row["last_message_id"] if row else 0) or 0
        if last_id > existing:
            conn.execute(
                "UPDATE channels SET last_message_id=? WHERE id=?", (last_id, channel_id)
            )


def existing_post_ids(channel_id):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ext_post_id FROM posts WHERE channel_id=?", (channel_id,)
        ).fetchall()
        return {r["ext_post_id"] for r in rows}


def insert_post(channel_id, post) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO posts(channel_id, ext_post_id, date, text, url, title) "
            "VALUES(?,?,?,?,?,?)",
            (
                channel_id,
                post["ext_post_id"],
                post.get("date", ""),
                post.get("text", ""),
                post.get("url", ""),
                post.get("title"),
            ),
        )


def _normalize(text: str) -> str:
    # lower() в SQLite не знает Юникод, поэтому нормализуем дубли на стороне Python
    return " ".join((text or "").strip().lower().split())


def insert_item(channel_id, post_ext_id, category, content, source_url, date) -> bool:
    """Вставляет пункт, пропуская точные дубли. True, если реально добавлен."""
    norm = _normalize(content)
    with _conn() as conn:
        existing = conn.execute(
            "SELECT content FROM items WHERE channel_id=? AND category=?",
            (channel_id, category),
        ).fetchall()
        if any(_normalize(r["content"]) == norm for r in existing):
            return False
        conn.execute(
            "INSERT INTO items(channel_id, post_ext_id, category, content, source_url, "
            "date, created_at) VALUES(?,?,?,?,?,?,?)",
            (
                channel_id,
                str(post_ext_id),
                category,
                content,
                source_url,
                date,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        return True


def items_for_channel(channel_id, category):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT content, source_url, date FROM items "
            "WHERE channel_id=? AND category=? ORDER BY date",
            (channel_id, category),
        ).fetchall()
        return [(r["content"], r["source_url"], r["date"]) for r in rows]


def list_channels():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, username, title FROM channels ORDER BY added_at"
        ).fetchall()
        out = []
        for r in rows:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM items WHERE channel_id=?", (r["id"],)
            ).fetchone()["n"]
            out.append((r["id"], r["platform"], r["username"], r["title"], n))
        return out


def get_channel_by_username(username, platform=None):
    with _conn() as conn:
        if platform:
            r = conn.execute(
                "SELECT id, username, title FROM channels "
                "WHERE username=? COLLATE NOCASE AND platform=?",
                (username, platform),
            ).fetchone()
        else:
            r = conn.execute(
                "SELECT id, username, title FROM channels WHERE username=? COLLATE NOCASE",
                (username,),
            ).fetchone()
        return (r["id"], r["username"], r["title"]) if r else None


def search_items(query, limit=20):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT i.category, i.content, i.source_url, ch.username "
            "FROM items i JOIN channels ch ON ch.id = i.channel_id "
            "WHERE i.content LIKE ? ORDER BY i.created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [
            (r["category"], r["content"], r["source_url"], r["username"]) for r in rows
        ]
