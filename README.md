# Knowledge Bot — извлечение знаний из Telegram-каналов

Telegram-бот для VPS: кидаешь ему ссылку на публичный канал — он выкачивает посты,
прогоняет их через нейросеть (**DeepSeek**) и достаёт **факты**, **ссылки на
исследования**, **техники**, **рекомендации/лайфхаки** и **интересную информацию**.
Всё складывается в локальную базу («память») и выгружается в Markdown-файлы.

> YouTube/Instagram/VK — следующий этап. Сейчас MVP только по Telegram.

## Как это работает

```
  Ты в личке боту:  https://t.me/friendshipwithbrain
            │
            ▼
   ┌────────────────────── VPS ──────────────────────┐
   │  Telethon-бот   ── интерфейс (команды, ответы)    │
   │      │                                            │
   │  Telethon userbot ── выкачивает историю канала    │
   │      │                                            │
   │  DeepSeek API   ── извлечение знаний → JSON        │
   │      │                                            │
   │  SQLite («память») + экспорт в Markdown           │
   └──────────────────────────────────────────────────┘
            │
            ▼
   Бот присылает: facts.md / research.md / techniques.md / ...
```

**Зачем userbot отдельно от бота?** Обычный бот (Bot API) не может читать историю
чужого канала — только там, где он админ. Поэтому чтение идёт через userbot
(твой аккаунт, Telethon), а бот отвечает за интерфейс.

## Установка на VPS

```bash
git clone <repo> /opt/knowledgebot
cd /opt/knowledgebot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env            # заполнить ключи (см. ниже)
```

### Что положить в `.env`

| Переменная | Где взять |
|---|---|
| `TG_API_ID`, `TG_API_HASH` | https://my.telegram.org → API development tools |
| `TG_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` |
| `ALLOWED_USER_IDS` | твой Telegram id у [@userinfobot](https://t.me/userinfobot) |
| `DEEPSEEK_API_KEY` | https://platform.deepseek.com |

### Первый вход userbot (один раз)

```bash
python login.py     # спросит номер телефона и код из Telegram
```

Создастся `data/userbot.session`. После этого можно запускать бота.

### Запуск

```bash
python main.py
```

Напиши боту в личку — пришли ссылку на канал.

### Автозапуск через systemd

```bash
sudo cp deploy/knowledgebot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now knowledgebot
journalctl -u knowledgebot -f      # логи
```

## Команды бота

| Команда | Что делает |
|---|---|
| ссылка на канал | разобрать канал и прислать выжимку |
| `/list` | какие каналы уже разобраны и сколько пунктов |
| `/digest <канал>` | прислать выжимку по каналу заново |
| `/search <слово>` | поиск по всей накопленной базе |

## Как устроен мониторинг

База помнит `last_message_id` каждого канала. При первом разборе берутся
последние `INITIAL_FETCH_LIMIT` постов (по умолчанию 150), при повторной отправке
той же ссылки — **только новые посты**. Так что «следить за каналом» = время от
времени присылать боту ту же ссылку (или повесить напоминание/cron, который
дёргает разбор — добавим позже).

## Выбор модели

По умолчанию `DEEPSEEK_MODEL=deepseek-chat` (актуальная чат-модель DeepSeek,
OpenAI-совместимый API). Задача «вытащить факты/техники» простая, поэтому
дорогую модель брать не нужно. Сменить модель/провайдера — одна строка в `.env`
(`DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_API_KEY`), код менять не надо.

## Структура

```
main.py                 точка входа (запуск бота)
login.py                одноразовый вход userbot
app/
  config.py             конфиг из .env
  bot.py                интерфейс + оркестрация
  collector.py          сбор постов (Telethon)
  extractor.py          извлечение знаний (DeepSeek)
  prompts.py            промпты и категории
  db.py                 SQLite-хранилище
  markdown_export.py    экспорт в Markdown
deploy/
  knowledgebot.service  unit для systemd
```

## Ограничения / честные оговорки

- Только **публичные** каналы.
- Категория «исследования» наполняется лишь тем, что **явно упомянуто** в тексте —
  модель проинструктирована не выдумывать источники. Но проверять первоисточники
  всё равно стоит.
- Скрейпинг контента может противоречить правилам платформы — для личного
  использования обычно ок, для продукта оцени риски сам.
