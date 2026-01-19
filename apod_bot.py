import logging
import re
import datetime
import requests
import os
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    AIORateLimiter,
)
from pytz import timezone

# === НАСТРОЙКИ ===
NASA_URL = "https://apod.nasa.gov/apod/astropix.html"
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AstronomyPictureofDay")

# === ЛОГГИРОВАНИЕ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ЭКРАНИРОВАНИЕ ДЛЯ MARKDOWN V2 ===
def escape_markdown(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

# === ПАРСИНГ САЙТА NASA ===
def fetch_apod_data():
    response = requests.get(NASA_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("b")
    title = title_tag.text.strip() if title_tag else "Astronomy Picture of the Day"

    explanation_tag = soup.find_all("p")[2]
    explanation = explanation_tag.text.strip()

    image_tag = soup.find("a", href=True)
    high_res_url = None
    if image_tag and (".jpg" in image_tag['href'] or ".png" in image_tag['href']):
        high_res_url = "https://apod.nasa.gov/apod/" + image_tag["href"]

    image_element = soup.find("img")
    preview_url = None
    if image_element:
        preview_url = "https://apod.nasa.gov/apod/" + image_element["src"]

    credit = ""
    credit_match = soup.find_all("b")
    if len(credit_match) >= 2:
        credit_text = credit_match[1].text.strip()
        credit = f"Image Credit: {credit_text}"

    headline = title.replace("\n", "").strip()

    return headline, explanation, preview_url, high_res_url, credit

# === ОТПРАВКА ПОСТА В КАНАЛ ===
async def send_apod_post(context: ContextTypes.DEFAULT_TYPE):
    headline, explanation, preview_url, _, credit = fetch_apod_data()

    today = datetime.datetime.now(timezone("Europe/Vilnius")).strftime("%d %B %Y")

    escaped_headline = escape_markdown(headline)
    escaped_credit = escape_markdown(credit)
    escaped_explanation = escape_markdown(explanation)

    caption = (
        f"*{escaped_headline}*\n"
        f"{escaped_credit}\n\n"
        f"{escaped_explanation}"
    )

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

# === КОМАНДЫ ===
async def start(update, context):
    await update.message.reply_text("Bot is running. Use /today to post. Auto posts at 09:00 (Vilnius).")

async def today(update, context):
    await send_apod_post(context)

# === ЗАПУСК ===
def main():
    app = ApplicationBuilder()\
        .token(TELEGRAM_TOKEN)\
        .rate_limiter(AIORateLimiter())\
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))

    app.job_queue.run_daily(
        send_apod_post,
        time=datetime.time(hour=9, minute=0, tzinfo=timezone("Europe/Vilnius"))
    )

    logger.info("Бот запущен. Автопост в 09:00 (Europe/Vilnius).")
    app.run_polling()


if __name__ == "__main__":
    main()
