"""Извлечение знаний из постов через DeepSeek (OpenAI-совместимый API)."""
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
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


async def extract_items(posts):
    """Принимает список постов, возвращает список сырых пунктов от модели.

    Каждый пункт: {"post_id", "category", "content", "link"?}.
    """
    items = []
    for batch in _chunks(posts, config.EXTRACT_BATCH_SIZE):
        user_prompt = build_user_prompt(batch)
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
            data = _parse_json(resp.choices[0].message.content or "")
        except Exception as exc:  # noqa: BLE001 — одна битая пачка не должна валить всё
            print(f"[extractor] пропускаю пачку из-за ошибки: {exc}")
            continue
        for item in data.get("items", []):
            if isinstance(item, dict):
                items.append(item)
    return items
