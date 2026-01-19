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

    # Попытка получить ссылку из <a>
    media_tag = soup.find("a")
    image_url = None

    if media_tag and media_tag["href"].endswith((".jpg", ".png")):
        image_url = "https://apod.nasa.gov/apod/" + media_tag["href"]
    else:
        # Попытка найти <img src=...>
        img_tag = soup.find("img")
        if img_tag and img_tag["src"].endswith((".jpg", ".png")):
            image_url = "https://apod.nasa.gov/apod/" + img_tag["src"]

    if image_url:
        image_data = requests.get(image_url).content
        return image_data, explanation
    else:
        return None, explanation

# ========== КОМАНДА /today ==========
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📡 Получаю Astronomy Picture of the Day...")
    image, text = get_apod_data()

    if not image:
        await update.message.reply_text("Сегодня изображение недоступно.")
        return

    vilnius_tz = timezone("Europe/Vilnius")
    today_str = datetime.now(vilnius_tz).strftime("%d %B %Y")

    caption = f"🗓 Astronomy Picture of the Day – {today_str}\n\n"
    caption += text[:1024 - len(caption)]

    # 1. Отправляем фото с подписью
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=image,
        caption=caption
    )

    # 2. Отправляем оригинал без сжатия
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=image,
        filename=f"apod_{today_str.replace(' ', '_')}.jpg",
        caption="📎 Изображение в оригинальном качестве"
    )

# ========== АВТОПОСТ В КАНАЛ ==========
def scheduled_post(application):
    image, text = get_apod_data()
    if not image:
        return

    vilnius_tz = timezone("Europe/Vilnius")
    today_str = datetime.now(vilnius_tz).strftime("%d %B %Y")

    caption = f"🗓 Astronomy Picture of the Day – {today_str}\n\n"
    caption += text[:1024 - len(caption)]

    # 1. Отправляем как фото с описанием
    application.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=image,
        caption=caption
    )

    # 2. Отправляем то же изображение как файл
    application.bot.send_document(
        chat_id=CHANNEL_ID,
        document=image,
        filename=f"apod_{today_str.replace(' ', '_')}.jpg",
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
