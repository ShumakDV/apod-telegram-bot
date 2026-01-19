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

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AstronomyPictureofDay")
NASA_APOD_URL = "https://apod.nasa.gov/apod/astropix.html"
BASE_URL = "https://apod.nasa.gov/apod/"

# ========== ЛОГИ ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== НАДЁЖНЫЙ ПОИСК ОРИГИНАЛА ==========
def get_apod_data():
    response = requests.get(NASA_APOD_URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    explanation = soup.find_all("p")[2].get_text()

    # Все возможные ссылки на изображения
    candidate_urls = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.lower().endswith((".jpg", ".jpeg", ".png", ".tiff")):
            full_url = BASE_URL + href
            candidate_urls.append(full_url)

    if not candidate_urls:
        return None, explanation, None

    # Выбираем самую "тяжёлую" ссылку
    max_size = -1
    best_url = None
    for url in candidate_urls:
        try:
            head = requests.head(url)
            size = int(head.headers.get("Content-Length", 0))
            logger.info(f"Checked {url} – {size/1024:.1f} KB")
            if size > max_size:
                max_size = size
                best_url = url
        except Exception as e:
            logger.warning(f"Ошибка при проверке {url}: {e}")

    if best_url:
        image_data = requests.get(best_url).content
        filename = best_url.split("/")[-1]
        logger.info(f"Выбран оригинал: {best_url} ({max_size/1024:.1f} KB)")
        return image_data, explanation, filename

    return None, explanation, None


# ========== /today ==========
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

    # 1. Фото (Telegram может сжать)
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=image,
        caption=caption
    )

    # 2. Оригинал (без сжатия)
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=image,
        filename=filename,
        caption="📎 Оригинальное изображение (без сжатия)"
    )


# ========== АВТОПОСТ ==========
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

    print("✅ Бот запущен. Оригинал изображения теперь действительно оригинальный.")
    application.run_polling()


if __name__ == "__main__":
    main()
