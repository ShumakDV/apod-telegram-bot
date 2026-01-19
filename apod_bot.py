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
)
from pytz import timezone

# ================= НАСТРОЙКИ =================
NASA_URL = "https://apod.nasa.gov/apod/astropix.html"
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AstronomyPictureofDay")

# ================= ЛОГИ =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= MARKDOWN V2 =================
def escape_md(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

# ================= PARSE APOD =================
def fetch_apod_data():
    response = requests.get(NASA_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    title = soup.find("b").text.strip()
    credit = ""
    bolds = soup.find_all("b")
    if len(bolds) > 1:
        credit = "Image Credit: " + bolds[1].text.strip()

    explanation = soup.find_all("p")[2].text.strip()

    img = soup.find("img")
    image_url = "https://apod.nasa.gov/apod/" + img["src"]

    return title, credit, explanation, image_url

# ================= SEND POST =================
async def send_apod_post(context: ContextTypes.DEFAULT_TYPE):
    title, credit, explanation, image_url = fetch_apod_data()

    title_md = escape_md(title)
    credit_md = escape_md(credit)
    explanation_md = escape_md(explanation)

    # 🔹 КОРОТКИЙ CAPTION (БЕЗ ОШИБОК)
    caption = f"*{title_md}*\n{credit_md}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 View on NASA Website", url=NASA_URL)]
    ])

    # 1️⃣ Фото
    await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=image_url,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )

    # 2️⃣ Полный текст ОТДЕЛЬНО
    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=explanation_md,
        parse_mode=ParseMode.MARKDOWN_V2
    )

# ================= COMMANDS =================
async def today(update, context):
    await send_apod_post(context)

async def start(update, context):
    await update.message.reply_text("Bot is running. Use /today.")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))

    app.job_queue.run_daily(
        send_apod_post,
        time=datetime.time(hour=9, minute=0, tzinfo=timezone("Europe/Vilnius"))
    )

    logger.info("Bot started. Auto post at 09:00 Vilnius time.")
    app.run_polling()

if __name__ == "__main__":
    main()
