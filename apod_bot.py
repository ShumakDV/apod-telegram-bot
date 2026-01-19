import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
import logging

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AstronomyPictureofDay")
NASA_APOD_URL = "https://apod.nasa.gov/apod/astropix.html"

# ========== ЛОГИ ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== ПОЛУЧЕНИЕ ИЗОБРАЖЕНИЯ ==========
def get_apod_data():
    response = requests.get(NASA_APOD_URL)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    explanation = soup.find_all("p")[2].get_text()

    # Ищем ссылку на оригинал изображения
    links = soup.find_all("a")
    image_url = None

    for link in links:
        href = link.get("href", "")
        if href.lower().endswith((".jpg", ".jpeg", ".png", ".tiff")):
            image_url = "https://apod.nasa.gov/apod/" + href
            break

    if image_url:
        image_data = requests.get(image_url).content
        filename = image_url.split("/")[-1]
        return image_data, explanation, filename
    else:
        return None, explanation, None

# ========== КОМАНДА /today ==========
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📡 Получаю Astronomy Picture of the Day...")
    image, text, filename = get_apod_data()

    if not image:
        await update.message.reply_text("Сегодня изображение недоступно.")
        return

    vilnius_tz = timezone("Europe/Vilnius")
    today_str = datetime.now(vilnius_tz).strftime("%d %B %Y")

    caption = f"🗓 Astronomy Picture of the Day – {today_str}\n\n"
    caption += text[:1024 - len(caption)]

    # 1. Отправляем фото с описанием
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=image,
        caption=caption
    )

    # 2. Отправляем оригинал как файл
    filename = filename or f"apod_{today_str.replace(' ', '_')}.jpg"
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=image,
        filename=filename,
        caption="🌃 Изображение в оригинальном качестве"
    )

# ========== АВТОПОСТ В КАНАЛ ==========
def scheduled_post(application):
    image, text, filename = get_apod_data()
    if not image:
        return

    vilnius_tz = timezone("Europe/Vilnius")
    today_str = datetime.now(vilnius_tz).strftime("%d %B %Y")

    caption = f"🗓 Astronomy Picture of the Day – {today_str}\n\n"
    caption += text[:1024 - len(caption)]

    # 1. Отправляем как фото
    application.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=image,
        caption=caption
    )

    # 2. Отправляем оригинальный файл
    filename = filename or f"apod_{today_str.replace(' ', '_')}.jpg"
    application.bot.send_document(
        chat_id=CHANNEL_ID,
        document=image,
        filename=filename,
        caption="📎 Изображение в оригинальном качестве"
    )

# ========== ЗАПУСК ==========
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

    print("✅ Бот запущен. Команда /today работает. Автопост в 6:00.")
    application.run_polling()

if __name__ == "__main__":
    main()
