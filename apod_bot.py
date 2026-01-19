import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AstronomyPictureofDay")
NASA_APOD_URL = "https://apod.nasa.gov/apod/astropix.html"
NASA_POST_BASE_URL = "https://apod.nasa.gov/apod/"

# ========== ЛОГИ ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== ПОЛУЧЕНИЕ ДАННЫХ ==========
def get_apod_data():
    response = requests.get(NASA_APOD_URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # Заголовок и автор
    try:
        title = soup.find_all("b")[0].text.strip()
        credit = soup.find_all("b")[1].next_sibling.strip().replace(":", "").replace("\n", "")
    except Exception:
        title = ""
        credit = ""

    # Текст объяснения
    explanation = soup.find_all("p")[2].get_text().strip()

    # Картинка
    img_tag = soup.find("img")
    image_url = None

    if img_tag and img_tag.get("src"):
        image_url = NASA_POST_BASE_URL + img_tag["src"]

    image_data = requests.get(image_url).content if image_url else None
    filename = image_url.split("/")[-1] if image_url else None

    return image_data, title, credit, explanation, filename


# ========== ССЫЛКА НА СЕГОДНЯ ==========
def generate_nasa_link():
    today = datetime.utcnow()
    short_date = today.strftime("%y%m%d")  # например: 260119
    return f"{NASA_POST_BASE_URL}ap{short_date}.html"


# ========== /today ==========
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📡 Fetching Astronomy Picture of the Day…")

    image, title, credit, text, filename = get_apod_data()
    if not image:
        await update.message.reply_text("Image is not available today.")
        return

    tz = timezone("Europe/Vilnius")
    today_str = datetime.now(tz).strftime("%d %B %Y")

    caption = f"🗓 Astronomy Picture of the Day – {today_str}\n\n"
    if title:
        caption += f"**{title}**\n"
    if credit:
        caption += f"*Image Credit: {credit}*\n\n"
    caption += text[:1024 - len(caption)]

    buttons = [
        [InlineKeyboardButton("🌐 View on NASA Website", url=generate_nasa_link())]
    ]
    markup = InlineKeyboardMarkup(buttons)

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=image,
        caption=caption,
        reply_markup=markup,
        parse_mode="Markdown"
    )


# ========== АВТОПОСТ ==========
def scheduled_post(application):
    image, title, credit, text, filename = get_apod_data()
    if not image:
        return

    tz = timezone("Europe/Vilnius")
    today_str = datetime.now(tz).strftime("%d %B %Y")

    caption = f"🗓 Astronomy Picture of the Day – {today_str}\n\n"
    if title:
        caption += f"**{title}**\n"
    if credit:
        caption += f"*Image Credit: {credit}*\n\n"
    caption += text[:1024 - len(caption)]

    buttons = [
        [InlineKeyboardButton("🌐 View on NASA Website", url=generate_nasa_link())]
    ]
    markup = InlineKeyboardMarkup(buttons)

    application.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=image,
        caption=caption,
        reply_markup=markup,
        parse_mode="Markdown"
    )


# ========== ЗАПУСК ==========
def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("today", today))

    scheduler = BackgroundScheduler(timezone=timezone("Europe/Vilnius"))
    scheduler.add_job(
        scheduled_post,
        "cron",
        hour=9,
        minute=0,
        args=[application],
    )
    scheduler.start()

    print("✅ Bot is running. Posting at 09:00 with formatted header and inline button.")
    application.run_polling()


if __name__ == "__main__":
    main()
