"""Экспорт накопленных пунктов канала в Markdown-файлы по категориям."""
import datetime
import os

from app import config, db
from app.prompts import CATEGORY_FILES, CATEGORY_TITLES


def export_channel(channel_id, username, title):
    """Пишет по файлу на категорию. Возвращает список созданных путей."""
    folder = os.path.join(config.OUTPUT_DIR, username or str(channel_id))
    os.makedirs(folder, exist_ok=True)
    today = datetime.date.today().isoformat()
    files = []

    for category, filename in CATEGORY_FILES.items():
        rows = db.items_for_channel(channel_id, category)
        if not rows:
            continue
        lines = [
            f"# {CATEGORY_TITLES[category]} — {title}",
            "",
            f"_Канал: @{username} · обновлено {today} · пунктов: {len(rows)}_",
            "",
        ]
        for content, url, date in rows:
            day = date[:10] if date else ""
            date_str = f" _( {day} )_" if day else ""
            src = f" — [источник]({url})" if url else ""
            lines.append(f"- {content}{date_str}{src}")

        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        files.append(path)

    return files
