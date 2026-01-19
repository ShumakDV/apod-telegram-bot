
import os
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone as tz

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токены и данные из переменных окружения
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Основная функция для парсинга данных APOD
def get_apod_data():
    url = "https://apod.nasa.gov/apod/astropix.html"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # Заголовок
    title = soup.find_all("b")[0].text.strip()

    # Автор (Image Credit)
    credit = "NASA"
    for tag in soup.find_all("center"):
        if "Image Credit" in tag.text:
            credit = tag.text.split("Image Credit:")[-1].strip()
            break

    # Описание
    explanation_block = soup.find("b", string="Explanation:")
    explanation_lines = []
    if explanation_block:
        for sibling in explanation_block.next_siblings:
            if sibling.name == "b":
                break
            if isinstance(sibling, str):
                explanation_lines.append(sibling.strip())
    explanation = "\n".join(line for line in explanation_lines if line)

    # Ссылка на изображение
    image_tag = soup.find("a", href=True)
    image_url = f"https://apod.nasa.gov/apod/{image_tag['href']}" if image_tag else None

    # Ссылка на страницу дня
    today = datetime.now(timezone.utc)
    page_url = f"https://apod.nasa.gov/apod/ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "explanation": explanation,
        "image_url": image_url,
        "page_url": page_url
    }

# Функция сборки текста поста
def build_post_text(data):
    now = datetime.now(timezone.utc).astimezone(tz("Europe/Vilnius"))
    return (
        f"*Astronomy Picture of the Day – {now.strftime('%d %B %Y')}*\n\n"
        f"*{data['title']}*\n"
        f"_Image Credit: {data['credit']}_\n\n"
        f"{data['explanation']}"
    )

# Команда /today для личных сообщений
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_apod_data()
    text = build_post_text(data)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]
    ])

    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=data["image_url"],
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка при /today: {e}")

# Автоматическая отправка в канал
async def send_apod_post(context: ContextTypes.DEFAULT_TYPE = None):
    data = get_apod_data()
    text = build_post_text(data)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]
    ])

    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=data["image_url"],
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        logger.info("✅ Пост отправлен в канал.")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке в канал: {e}")

# Запуск бота
async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Команда /today
    app.add_handler(CommandHandler("today", today))

    # Планировщик
    scheduler = AsyncIOScheduler(timezone="Europe/Vilnius")
    scheduler.add_job(send_apod_post, trigger="cron", hour=9, minute=0)
    scheduler.start()
    logger.info("🕓 Планировщик запущен")

    # Запуск бота
    logger.info("✅ Бот запущен. Ожидает команды или автоматическую отправку.")
    await app.run_polling()

# Совместимость с Railway (если event loop уже запущен)
if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise
