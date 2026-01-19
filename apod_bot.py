import os
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, time
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from pytz import timezone as tz

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

APOD_URL = "https://apod.nasa.gov/apod/astropix.html"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ПАРСИНГ APOD ==================

def get_apod_data():
    response = requests.get(APOD_URL, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Заголовок
    title = soup.find_all("b")[0].get_text(strip=True)

    # Image Credit (реальный автор)
    credit = "NASA"
    for center in soup.find_all("center"):
        if "Image Credit" in center.text:
            credit = center.text.split("Image Credit:")[-1].strip()
            break

    # Explanation
    explanation = ""
    expl_tag = soup.find("b", string="Explanation:")
    if expl_tag:
        parts = []
        for el in expl_tag.next_siblings:
            if getattr(el, "name", None) == "b":
                break
            if isinstance(el, str):
                text = el.strip()
                if text:
                    parts.append(text)
        explanation = " ".join(parts)

    # Оригинальная картинка
    image_url = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith((".jpg", ".jpeg", ".png")):
            image_url = "https://apod.nasa.gov/apod/" + href
            break

    if not image_url:
        raise RuntimeError("Не удалось найти изображение APOD")

    # Ссылка на сегодняшний пост
    today = datetime.now(timezone.utc)
    page_url = f"https://apod.nasa.gov/apod/ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "explanation": explanation,
        "image_url": image_url,
        "page_url": page_url,
    }

# ================== ТЕКСТ ПОСТА ==================

def build_caption(data):
    now = datetime.now(timezone.utc).astimezone(tz("Europe/Vilnius"))
    caption = (
        f"*Astronomy Picture of the Day – {now.strftime('%d %B %Y')}*\n\n"
        f"*{data['title']}*\n"
        f"_Image Credit: {data['credit']}_\n\n"
        f"{data['explanation']}"
    )

    # лимит Telegram
    if len(caption) > 1024:
        caption = caption[:1020] + "..."

    return caption

# ================== ОТПРАВКА ==================

async def send_apod(chat_id: str, bot):
    data = get_apod_data()
    caption = build_caption(data)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]
    ])

    await bot.send_photo(
        chat_id=chat_id,
        photo=data["image_url"],
        caption=caption,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ================== /today ==================

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_apod(update.effective_chat.id, context.bot)

# ================== АВТОПОСТ ==================

async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await send_apod(CHANNEL_ID, context.bot)
    logger.info("✅ Автопост отправлен в канал")

# ================== ЗАПУСК ==================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Команда /today
    app.add_handler(CommandHandler("today", today))

    # Планирование автопоста (09:00 Вильнюс)
    vilnius_tz = tz("Europe/Vilnius")
    app.job_queue.run_daily(
        daily_post,
        time=time(hour=9, minute=0, tzinfo=vilnius_tz)
    )

    logger.info("✅ Бот запущен. /today — в личку, автопост — в канал.")
    app.run_polling()

if __name__ == "__main__":
    main()
