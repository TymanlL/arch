"""Загрузка конфигурации из переменных окружения / .env."""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


TG_API_ID = _int("TG_API_ID", 0)
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

ALLOWED_USER_IDS = {
    int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x
}

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN", "")
VK_API_VERSION = os.getenv("VK_API_VERSION", "5.199")

DB_PATH = os.getenv("DB_PATH", "data/knowledge.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
USERBOT_SESSION = os.getenv("USERBOT_SESSION", "data/userbot")
BOT_SESSION = os.getenv("BOT_SESSION", "data/bot")

INITIAL_FETCH_LIMIT = _int("INITIAL_FETCH_LIMIT", 150)
EXTRACT_BATCH_SIZE = _int("EXTRACT_BATCH_SIZE", 10)
# Максимум символов одного источника, отправляемого модели (защита от
# гигантских расшифровок видео). Лишнее обрезается.
EXTRACT_MAX_CHARS = _int("EXTRACT_MAX_CHARS", 16000)


def validate() -> None:
    """Падаем рано и понятно, если чего-то не хватает."""
    required = {
        "TG_API_ID": TG_API_ID,
        "TG_API_HASH": TG_API_HASH,
        "TG_BOT_TOKEN": TG_BOT_TOKEN,
        "DEEPSEEK_API_KEY": DEEPSEEK_API_KEY,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Не заданы переменные окружения: "
            + ", ".join(missing)
            + ". Скопируй .env.example в .env и заполни."
        )
