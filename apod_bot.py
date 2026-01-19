import logging
import os
import re
import datetime
import requests
from bs4 import BeautifulSoup
from telegram import InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

# === НАСТРОЙКИ ===
NASA_URL = "https://apod.nasa.gov/apod/astropix.html"
TELEGRAM_TOKEN = "ВАШ_ТОКЕН"
CHANNEL_ID = "@AstronomyPictureofDay"

# === НАСТРОЙКА ЛОГГЕРА ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def escape_markdown(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

def fetch_apod_data():
    response = requests.get(NASA_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("b")
    title = title_tag.text.strip() if title_tag else "Astronomy Picture of the Day"

    explanation_tag = soup.find_all("p")[2]
    explanation = explanation_tag.text.strip()

    image_tag = soup.find("a", href=True)
    if image_tag and (".jpg" in image_tag['href'] or ".png" in image_tag['href']):
        high_res_url = "https://apod.nasa.gov/apod/" + image_tag["href"]
    else:
        high_res_url = None

    image_element = soup.find("img")
    if image_element:
        preview_url = "https://apod.nasa.gov/apod/" + image_element["src"]
    else:
        preview_url = None

    credit = ""
    credit_match = soup.find_all("b")
    if len(credit_match) >= 2:
        credit_text = credit_match[1].text.strip()
        credit = f"Image Credit: {credit_text}"

    headline = title.replace("\n", "").strip()

    return headline, explanation, preview_url, high_res_url, credit

async def send_apod_post(context: ContextTypes.DEFAULT_TYPE):
    headline, explanation, preview_url, high_res_url, credit = fetch_apod_data()

    today = datetime.datetime.now(timezone("Europe/Vilnius")).strftime("%d %B %Y")
    post_title = f"Astronomy Picture of the Day – {today}"

    # Экранируем текст
    escaped_title = escape_markdown(post_title)
    escaped_headline = escape_markdown(headline)
    escaped_credit = escape_markdown(credit)
    escaped_explanation = escape_markdown(explanation)

    caption = f"*{escaped_headline}*\n{escaped_credit}\n\n{escaped_explanation}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 View on NASA Website", url=NASA_URL)]
    ])

    if preview_url:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=preview_url,
            caption=caption,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=caption,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

# === ОБРАБОТЧИКИ ===
async def start(update, context):
    await update.message.reply_text("Бот запущен. Команда /today доступна. Автопост в 9:00.")

async def today(update, context):
    await send_apod_post(context)

# === ГЛАВНАЯ ===
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))

    # Планировщик
    scheduler = AsyncIOScheduler(timezone="Europe/Vilnius")
    scheduler.add_job(send_apod_post, trigger="cron", hour=9, minute=0, args=[app])
    scheduler.start()

    logger.info("Бот запущен. Команда /today доступна. Автопост в 9:00.")
    app.run_polling()

if __name__ == "__main__":
    main()
