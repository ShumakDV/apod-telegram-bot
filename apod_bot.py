import os
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, time
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from pytz import timezone as tz

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

APOD_URL = "https://apod.nasa.gov/apod/astropix.html"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ПАРСИНГ APOD ==================

def get_apod_data():
    response = requests.get(APOD_URL, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Заголовок
    title = soup.find_all("b")[0].get_text(strip=True)

    # Автор (Image Credit)
    credit = "NASA"
    for tag in soup.find_all("center"):
        if "Image Credit" in tag.text:
            credit = tag.text.split("Image Credit:")[-1].strip()
            break

    # Explanation (получаем весь блок)
    explanation_text = ""
    expl_tag = soup.find("b", string="Explanation:")
    if expl_tag:
        # собираем текст всех следующих строк до следующего <b>
        lines = []
        for sib in expl_tag.next_siblings:
            if getattr(sib, "name", None) == "b":
                break
            if isinstance(sib, str):
                text = sib.strip()
                if text:
                    lines.append(text)
        explanation_text = " ".join(lines)

    # делим на предложения
    sentences = explanation_text.split(". ")
    # берём первые 5 предложений
    first_sentences = ". ".join(sentences[:5]).strip()
    # если они не заканчиваются на точку — добавим
    if first_sentences and not first_sentences.endswith("."):
        first_sentences += "."

    # Оригинальная картинка
    image_url = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith((".jpg", ".jpeg", ".png")):
            image_url = "https://apod.nasa.gov/apod/" + href
            break

    # Ссылка на сегодняшний пост
    today = datetime.now(timezone.utc)
    page_url = f"https://apod.nasa.gov/apod/ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "image_url": image_url,
        "page_url": page_url,
        "short_explanation": first_sentences
    }

# ================== СБОРКА ПОДПИСИ ==================

def build_caption(data):
    now = datetime.now(timezone.utc).astimezone(tz("Europe/Vilnius"))
    caption = (
        f"*Astronomy Picture of the Day – {now.strftime('%d %B %Y')}*\n\n"
        f"*{data['title']}*\n"
        f"_Image Credit: {data['credit']}_\n\n"
        f"{data['short_explanation']}"
    )

    # Telegram лимит caption ≤ 1024 символа
    if len(caption) > 1024:
        caption = caption[:1020] + "..."

    return caption

# ================== ОТПРАВКА ==================

async def send_apod(chat_id: str, bot):
    data = get_apod_data()
    caption = build_caption(data)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]
    ])

    await bot.send_photo(
        chat_id=chat_id,
        photo=data["image_url"],
        caption=caption,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ================== /today ==================

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_apod(update.effective_chat.id, context.bot)

# ================== АВТОПОСТ ==================

async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await send_apod(CHANNEL_ID, context.bot)
    logger.info("✅ Автопост отправлен в канал")

# ================== ЗАПУСК ==================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Команда /today
    app.add_handler(CommandHandler("today", today))

    # Планирование автопоста через JobQueue
    vilnius_tz = tz("Europe/Vilnius")
    app.job_queue.run_daily(
        daily_post,
        time=time(hour=9, minute=0, tzinfo=vilnius_tz)
    )

    logger.info("✅ Бот запущен. /today — в личку, автопост — в канал.")
    app.run_polling()

if __name__ == "__main__":
    main()
