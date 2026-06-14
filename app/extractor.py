"""Извлечение знаний из постов/видео через DeepSeek (OpenAI-совместимый API)."""
import json

from openai import AsyncOpenAI

from app import config
from app.prompts import SYSTEM_PROMPT, build_user_prompt

_client = AsyncOpenAI(
    api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL
)


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _parse_json(text):
    """Достаёт JSON-объект из ответа модели, терпимо к обёрткам/мусору."""
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _resolve_post(idx_map, raw_id):
    post = idx_map.get(raw_id)
    if post is None:
        try:
            post = idx_map.get(int(raw_id))
        except (TypeError, ValueError):
            post = None
    return post


async def extract_items(posts, batch_size=None):
    """Принимает список источников, возвращает список пунктов.

    Каждый пункт: {"category", "content", "link", "post"} — где post это исходный
    словарь поста/видео (с ext_post_id, url, date).
    """
    batch_size = batch_size or config.EXTRACT_BATCH_SIZE
    results = []
    for batch in _chunks(posts, batch_size):
        idx_map = {i: post for i, post in enumerate(batch, 1)}
        user_prompt = build_user_prompt(batch, config.EXTRACT_MAX_CHARS)
        try:
            resp = await _client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            data = _parse_json(resp.choices[0].message.content)
        except Exception as exc:  # noqa: BLE001 — одна битая пачка не должна валить всё
            print(f"[extractor] пропускаю пачку из-за ошибки: {exc}")
            continue
        for item in data.get("items", []):
            if not isinstance(item, dict):
                continue
            post = _resolve_post(idx_map, item.get("post_id"))
            if post is None:
                continue
            results.append(
                {
                    "category": item.get("category"),
                    "content": (item.get("content") or "").strip(),
                    "link": item.get("link"),
                    "post": post,
                }
            )
    return results
