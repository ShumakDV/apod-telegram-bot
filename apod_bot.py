import os
import logging
import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

# Включаем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен и ID канала из переменных окружения
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Только для автопостинга

# Функция парсинга страницы APOD
def get_apod_data():
    url = "https://apod.nasa.gov/apod/astropix.html"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # Заголовок изображения
    title = soup.find_all("b")[0].text.strip()

    # Автор изображения
    credit = "NASA"
    center_tags = soup.find_all("center")
    for tag in center_tags:
        if "Image Credit" in tag.text:
            if ":" in tag.text:
                credit = tag.text.split("Image Credit:")[-1].strip()
            break

    # Поиск первого текстового блока после Explanation:
    explanation_block = soup.find("b", string="Explanation:")
    explanation = ""
    if explanation_block:
        # Собираем все строки текста после тега Explanation
        explanation_lines = []
        for sibling in explanation_block.next_siblings:
            if sibling.name == "b":
                break
            if isinstance(sibling, str):
                explanation_lines.append(sibling.strip())
        explanation = "\n".join(line for line in explanation_lines if line)

    # Ссылка на изображение
    image_tag = soup.find("a", href=True)
    image_url = f"https://apod.nasa.gov/apod/{image_tag['href']}" if image_tag else None

    # Ссылка на страницу с постом
    today = datetime.utcnow()
    post_url = f"https://apod.nasa.gov/apod/ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "explanation": explanation,
        "image_url": image_url,
        "page_url": post_url
    }

# Функция отправки поста
async def send_apod_post(context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    try:
        data = get_apod_data()
        caption = (
            f"*Astronomy Picture of the Day – {datetime.utcnow().strftime('%d %B %Y')}*\n\n"
            f"*{data['title']}*\n"
            f"_Image Credit: {data['credit']}_\n\n"
            f"{data['explanation']}"
        )

        # Кнопка "Открыть на сайте NASA"
        button = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]
        ])

        # Определяем куда слать: в канал (если автопост) или в личку (если /today)
        destination = chat_id or CHANNEL_ID

        await context.bot.send_photo(
            chat_id=destination,
            photo=data["image_url"],
            caption=caption,
            reply_markup=button,
            parse_mode="Markdown"
        )
        logger.info(f"Пост успешно отправлен в {destination}")
    except Exception as e:
        logger.error(f"Ошибка при отправке поста: {e}")

# Обработка команды /today — в личные сообщения
async def today(update, context):
    await send_apod_post(context, chat_id=update.effective_chat.id)

# Основной запуск бота
async def main():
    # Создание экземпляра приложения
    app = Application.builder().token(BOT_TOKEN).build()

    # Планировщик для автоматической отправки каждый день в 09:00 (по Вильнюсу)
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Europe/Vilnius"))
    scheduler.add_job(send_apod_post, CronTrigger(hour=9, minute=0), args=[app.bot])
    scheduler.start()
    logger.info("Планировщик запущен")

    # Обработчик команды /today
    app.add_handler(CommandHandler("today", today))

    logger.info("Бот запущен. Ожидает команды или автоматическую отправку.")
    await app.run_polling()

# Запуск скрипта
if __name__ == "__main__":
    asyncio.run(main())
