import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone
import logging

# 📋 Логгирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔐 Переменные из Railway
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
APOD_URL = "https://apod.nasa.gov/apod/astropix.html"

# 📤 Получаем данные с NASA
def fetch_apod_data():
    response = requests.get(APOD_URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title = soup.find_all("b")[0].get_text(strip=True)
    credit_tag = soup.find("b", string="Image Credit")
    credit = credit_tag.next_sibling.strip(": ").strip() if credit_tag else "NASA"

    explanation = ""
    explanation_start = soup.find("b", string="Explanation:")
    if explanation_start:
        for tag in explanation_start.parent.find_next_siblings("p"):
            explanation += tag.get_text(" ", strip=True) + "\n\n"
            if len(explanation) > 1500:
                break

    image_tag = soup.find("a", href=True)
    image_url = f"https://apod.nasa.gov/apod/{image_tag['href']}" if image_tag else ""

    return {
        "title": title,
        "credit": credit,
        "explanation": explanation.strip(),
        "image_url": image_url
    }

# 📤 Отправляем пост
async def send_apod_post(context: ContextTypes.DEFAULT_TYPE):
    try:
        apod = fetch_apod_data()
        date_str = datetime.now().strftime("%d %B %Y")
        caption = (
            f"<b>Astronomy Picture of the Day – {date_str}</b>\n\n"
            f"<b>{apod['title']}</b>\n"
            f"<i>Image Credit: {apod['credit']}</i>\n\n"
            f"{apod['explanation']}"
        )

        if len(caption) > 1024:
            caption = caption[:1020] + "..."

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 View on NASA Website", url=APOD_URL)]
        ])

        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=apod["image_url"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=buttons
        )

        logger.info("Пост отправлен")

    except Exception as e:
        logger.error(f"Ошибка при отправке поста: {e}")

# 🔘 Обработчик команды /today
async def today(update, context):
    await send_apod_post(context)

# 🧠 post_init: запускаем планировщик после старта бота
async def start_scheduler(application):
    scheduler = AsyncIOScheduler(timezone=timezone("Europe/Vilnius"))
    scheduler.add_job(send_apod_post, trigger="cron", hour=9, minute=0, args=[application.bot])
    scheduler.start()
    logger.info("Планировщик запущен")

# 🚀 Основной запуск
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(start_scheduler).build()
    app.add_handler(CommandHandler("today", today))
    logger.info("Бот запущен. Автопост в 09:00 (Europe/Vilnius).")
    app.run_polling()

if __name__ == "__main__":
    main()
