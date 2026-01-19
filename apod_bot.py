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
import re

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

APOD_URL = "https://apod.nasa.gov/apod/astropix.html"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ПАРСИНГ APOD ==================

def get_apod_data():
    response = requests.get(APOD_URL, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # ---------- Заголовок ----------
    title = soup.find_all("b")[0].get_text(strip=True)

    # ---------- Image Credit ----------
    credit = "NASA"
    for center in soup.find_all("center"):
        if "Image Credit" in center.get_text():
            credit = center.get_text().split("Image Credit:")[-1].strip()
            break

    # ---------- Explanation ----------
    explanation_text = ""
    expl_b = soup.find("b", string="Explanation:")
    if expl_b:
        parts = []
        for sib in expl_b.next_siblings:
            if getattr(sib, "name", None) == "b":
                break
            if isinstance(sib, str):
                cleaned = sib.strip()
                if cleaned:
                    parts.append(cleaned)
        explanation_text = " ".join(parts)

    # чистим пробелы и переносы
    explanation_text = re.sub(r"\s+", " ", explanation_text)

    # ---------- Берём первые 2–3 предложения ----------
    sentences = re.split(r"(?<=\.)\s+", explanation_text)
    short_explanation = " ".join(sentences[:3]).strip()

    if short_explanation and not short_explanation.endswith("."):
        short_explanation += "."

    # ---------- Оригинальная картинка ----------
    image_url = None
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if href.endswith((".jpg", ".jpeg", ".png")):
            image_url = "https://apod.nasa.gov/apod/" + a["href"]
            break

    # ---------- Ссылка на страницу ----------
    today = datetime.now(timezone.utc)
    page_url = f"https://apod.nasa.gov/apod/ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "image_url": image_url,
        "page_url": page_url,
        "short_explanation": short_explanation,
    }

# ================== СБОРКА ПОДПИСИ ==================

def build_caption(data):
    now = datetime.now(timezone.utc).astimezone(tz("Europe/Vilnius"))

    caption = (
        f"*Astronomy Picture of the Day – {now.strftime('%d %B %Y')}*\n\n"
        f"*{data['title']}*\n"
        f"_Image Credit: {data['credit']}_\n\n"
        f"{data['short_explanation']}"
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

    # /today — в личку
    app.add_handler(CommandHandler("today", today))

    # автопост в 09:00 Вильнюс
    vilnius_tz = tz("Europe/Vilnius")
    app.job_queue.run_daily(
        daily_post,
        time=time(hour=9, minute=0, tzinfo=vilnius_tz)
    )

    logger.info("✅ Бот запущен. /today — в личку, автопост — в канал.")
    app.run_polling()

if __name__ == "__main__":
    main()
