
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

# 🔐 Переменные окружения
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
APOD_URL = "https://apod.nasa.gov/apod/astropix.html"

# 📥 Получаем данные APOD
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

    image_url = ""
    for a_tag in soup.find_all("a", href=True):
        href = a_tag['href']
        if href.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
            image_url = f"https://apod.nasa.gov/apod/{href}"
            break

    return {
        "title": title,
        "credit": credit,
        "explanation": explanation.strip(),
        "image_url": image_url
    }

# 🧠 Проверка доступности картинки
def is_valid_image(url):
    try:
        head = requests.head(url, timeout=10)
        content_type = head.headers.get("Content-Type", "")
        return content_type.startswith("image")
    except Exception as e:
        logger.error(f"Ошибка при проверке изображения: {e}")
        return False

# 📤 Отправка поста (в канал или ЛС)
async def send_apod_post(context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    try:
        apod = fetch_apod_data()

        if not apod["image_url"] or not is_valid_image(apod["image_url"]):
            logger.error("Недопустимый формат изображения или ссылка недоступна.")
            return

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

        target_chat = chat_id or CHANNEL_ID

        await context.bot.send_photo(
            chat_id=target_chat,
            photo=apod["image_url"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=buttons
        )
        logger.info(f"Пост отправлен в {target_chat}")

    except Exception as e:
        logger.error(f"Ошибка при отправке поста: {e}")

# 🔘 Команда /today отправляет пост в ЛС
async def today(update, context):
    await send_apod_post(context, chat_id=update.effective_chat.id)

# 📅 Планировщик
async def start_scheduler(app):
    scheduler = AsyncIOScheduler(timezone=timezone("Europe/Vilnius"))
    scheduler.add_job(send_apod_post, "cron", hour=9, minute=0, args=[app.bot])
    scheduler.start()
    logger.info("Планировщик запущен")

# 🚀 Запуск бота
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(start_scheduler).build()
    app.add_handler(CommandHandler("today", today))
    logger.info("Бот запущен. Автопост в 09:00 (Europe/Vilnius).")
    app.run_polling()

if __name__ == "__main__":
    main()
