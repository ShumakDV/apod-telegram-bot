import os
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен из переменной окружения (как настроено в Railway)
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # ID канала, если потребуется для автопоста

# Максимально допустимая длина подписи в Telegram
MAX_CAPTION_LENGTH = 1024

# Получение данных APOD с сайта NASA
def get_apod_data():
    url = "https://apod.nasa.gov/apod/astropix.html"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    title_tag = soup.find_all("b")[0]
    title = title_tag.text.strip()

    credit_line = soup.find_all("b")[1].next_sibling.strip() if len(soup.find_all("b")) > 1 else "Unknown"
    image_tag = soup.find("img")
    image_url = "https://apod.nasa.gov/apod/" + image_tag["src"] if image_tag else None

    explanation_header = soup.find("b", string="Explanation:")
    explanation = ""
    if explanation_header:
        for elem in explanation_header.next_siblings:
            if elem.name == "b":
                break
            if isinstance(elem, str):
                explanation += elem.strip() + "\n"

    today = datetime.now().strftime("%d %B %Y")
    nasa_page_url = "https://apod.nasa.gov/apod/astropix.html"

    return {
        "title": title,
        "credit": credit_line,
        "image_url": image_url,
        "explanation": explanation.strip(),
        "today": today,
        "nasa_url": nasa_page_url,
    }

# Отправка поста (для кнопки и автопостинга)
async def send_apod_post(context: CallbackContext):
    apod = get_apod_data()

    caption_header = f"<b>{apod['title']}</b>\n<i>Image Credit: {apod['credit']}</i>\n\n"
    explanation = apod['explanation']
    full_caption = caption_header + explanation

    keyboard = [
        [InlineKeyboardButton("🌐 View on NASA Website", url=apod['nasa_url'])]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if len(full_caption) <= MAX_CAPTION_LENGTH:
        # Всё помещается — отправляем в одном сообщении
        await context.bot.send_photo(
            chat_id=context.job.chat_id if hasattr(context, 'job') else context._chat_id,
            photo=apod['image_url'],
            caption=full_caption,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        # Подпись слишком длинная — делим на 2 части
        await context.bot.send_photo(
            chat_id=context.job.chat_id if hasattr(context, 'job') else context._chat_id,
            photo=apod['image_url'],
            caption=caption_header,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        await context.bot.send_message(
            chat_id=context.job.chat_id if hasattr(context, 'job') else context._chat_id,
            text=explanation,
            parse_mode='HTML'
        )

# Команда /today — получить пост за сегодня
async def today(update, context):
    context._chat_id = update.effective_chat.id
    await send_apod_post(context)

# Основная функция запуска бота
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Добавляем команду /today
    app.add_handler(CommandHandler("today", today))

    # Планируем автопост в 9:00 по Вильнюсу
    scheduler = AsyncIOScheduler(timezone="Europe/Vilnius")
    scheduler.add_job(
        send_apod_post,
        trigger=CronTrigger(hour=9, minute=0),
        kwargs={"context": CallbackContext(app).bot}
    )
    scheduler.start()

    logger.info("Бот запущен. Автопост в 09:00 (Europe/Vilnius).")
    app.run_polling()

if __name__ == "__main__":
    main()
