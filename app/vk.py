"""Сбор постов со стены ВКонтакте через открытый API (wall.get).

Нужен сервисный/пользовательский токен в VK_ACCESS_TOKEN. Функции синхронные —
в боте вызываются через asyncio.to_thread.
"""
import datetime
import json
import re
import urllib.parse
import urllib.request

from app import config

_API = "https://api.vk.com/method/"


def parse_target(text: str):
    """Из ссылки/имени ВК делает {'domain': ...} или {'owner_id': ...} или None."""
    t = (text or "").strip()
    t = re.sub(r"^https?://", "", t)
    t = re.sub(r"^(m\.|www\.)", "", t)
    for prefix in ("vk.com/", "vkontakte.ru/"):
        if t.startswith(prefix):
            t = t[len(prefix) :]
            break
    t = t.split("/")[0].split("?")[0].lstrip("@")
    if not t:
        return None
    m = re.fullmatch(r"(?:club|public|event)(\d+)", t)
    if m:
        return {"owner_id": -int(m.group(1))}
    m = re.fullmatch(r"id(\d+)", t)
    if m:
        return {"owner_id": int(m.group(1))}
    if re.fullmatch(r"[A-Za-z0-9_.]+", t):
        return {"domain": t}
    return None


def _api(method: str, params: dict):
    if not config.VK_ACCESS_TOKEN:
        raise RuntimeError("Не задан VK_ACCESS_TOKEN (см. .env)")
    query = {**params, "access_token": config.VK_ACCESS_TOKEN, "v": config.VK_API_VERSION}
    url = _API + method + "?" + urllib.parse.urlencode(query)
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(f"VK API: {data['error'].get('error_msg', data['error'])}")
    return data["response"]


def _owner_id(resp, target):
    if "owner_id" in target:
        return target["owner_id"]
    items = resp.get("items") or []
    if items:
        return items[0]["owner_id"]
    groups = resp.get("groups") or []
    profiles = resp.get("profiles") or []
    if groups:
        return -groups[0]["id"]
    if profiles:
        return profiles[0]["id"]
    raise RuntimeError("Не удалось определить владельца стены")


def _name(resp, owner):
    if owner < 0:
        for g in resp.get("groups", []):
            if g["id"] == -owner:
                return g.get("name", str(owner)), g.get("screen_name") or f"club{-owner}"
    else:
        for p in resp.get("profiles", []):
            if p["id"] == owner:
                name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
                return name or str(owner), p.get("screen_name") or f"id{owner}"
    return str(owner), str(owner)


def resolve(target):
    """Возвращает (ext_id, username, title) владельца стены."""
    resp = _api("wall.get", {**target, "count": 1, "extended": 1})
    owner = _owner_id(resp, target)
    title, username = _name(resp, owner)
    return str(owner), username, title


def collect_wall(target, full=False, last_id=0, known_ids=frozenset()):
    """Возвращает посты стены (старые -> новые).

    full=True  — вся стена, кроме уже сохранённых (known_ids).
    full=False — если last_id задан, всё новее него; иначе последние
                 INITIAL_FETCH_LIMIT постов.
    """
    posts = []
    offset = 0
    page = 100
    while True:
        resp = _api(
            "wall.get", {**target, "count": page, "offset": offset, "extended": 1}
        )
        items = resp.get("items") or []
        if not items:
            break
        stop = False
        for it in items:
            pid = it["id"]
            owner = it.get("owner_id")
            text = (it.get("text") or "").strip()
            if not full and last_id and pid <= last_id:
                stop = True
                break
            if full and str(pid) in known_ids:
                continue
            if text:
                ts = it.get("date")
                posts.append(
                    {
                        "ext_post_id": str(pid),
                        "text": text,
                        "url": f"https://vk.com/wall{owner}_{pid}",
                        "date": datetime.datetime.utcfromtimestamp(ts).isoformat()
                        if ts
                        else "",
                        "title": None,
                    }
                )
            if not full and not last_id and len(posts) >= config.INITIAL_FETCH_LIMIT:
                stop = True
                break
        if stop:
            break
        offset += page
        if offset >= resp.get("count", 0) or offset > 10000:
            break
    posts.reverse()  # wall.get отдаёт новые -> старые
    return posts
