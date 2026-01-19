import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone

# ================= НАСТРОЙКИ =================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AstronomyPictureofDay")
NASA_APOD_URL = "https://apod.nasa.gov/apod/astropix.html"
BASE_URL = "https://apod.nasa.gov/apod/"

# ================= ЛОГИ =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= APOD =================
def get_apod_data():
    response = requests.get(NASA_APOD_URL)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # ---- текст ----
    explanation = soup.find_all("p")[2].get_text()

    # ---- ИЩЕМ ОРИГИНАЛ ----
    image_url = None

    for a in soup.find_all("a"):
        img = a.find("img")
        if img and a.get("href", "").lower().endswith((".jpg", ".jpeg", ".png", ".tiff")):
            image_url = BASE_URL + a["href"]
            break

    if not image_url:
        return None, explanation, None

    logger.info(f"Original image found: {image_url}")

    image_data = requests.get(image_url).content
    filename = image_url.split("/")[-1]

    return image_data, explanation, filename


# ================= /today =================
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📡 Загружаю Astronomy Picture of the Day…")

    image, text, filename = get_apod_data()
    if not image:
        await update.message.reply_text("Сегодня изображение недоступно.")
        return

    tz = timezone("Europe/Vilnius")
    today_str = datetime.now(tz).strftime("%d %B %Y")

    caption = f"🗓 Astronomy Picture of the Day – {today_str}\n\n"
    caption += text[:1024 - len(caption)]

    # Фото (Telegram-сжатие — ок)
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=image,
        caption=caption
    )

    # ОРИГИНАЛ БЕЗ СЖАТИЯ
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=image,
        filename=filename,
        caption="📎 Оригинальное изображение (без сжатия)"
    )


# ================= АВТОПОСТ =================
def scheduled_post(application):
    image, text, filename = get_apod_data()
    if not image:
        return

    tz = timezone("Europe/Vilnius")
    today_str = datetime.now(tz).strftime("%d %B %Y")

    caption = f"🗓 Astronomy Picture of the Day – {today_str}\n\n"
    caption += text[:1024 - len(caption)]

    application.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=image,
        caption=caption
    )

    application.bot.send_document(
        chat_id=CHANNEL_ID,
        document=image,
        filename=filename,
        caption="📎 Оригинальное изображение (без сжатия)"
    )


# ================= ЗАПУСК =================
def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("today", today))

    scheduler = BackgroundScheduler(timezone=timezone("Europe/Vilnius"))
    scheduler.add_job(
        scheduled_post,
        "cron",
        hour=6,
        minute=0,
        args=[application],
    )
    scheduler.start()

    print("✅ APOD бот запущен. Оригиналы скачиваются корректно.")
    application.run_polling()


if __name__ == "__main__":
    main()
