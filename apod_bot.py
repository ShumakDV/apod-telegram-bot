import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone
import logging

# Включаем логгирование для отладки
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# URL страницы APOD
APOD_URL = "https://apod.nasa.gov/apod/astropix.html"


# 📥 Получаем данные с сайта APOD
def fetch_apod_data():
    response = requests.get(APOD_URL)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Заголовок картинки
    title_tag = soup.find_all("b")[0]
    title = title_tag.get_text(strip=True) if title_tag else "Astronomy Picture of the Day"

    # Автор изображения
    credit_text = ""
    credit_tag = soup.find("b", string="Image Credit")
    if credit_tag and credit_tag.next_sibling:
        credit_text = credit_tag.next_sibling.strip(": ").strip()

    # Пояснение (всё, что после тега <b>Explanation:</b>)
    explanation_start = soup.find("b", string="Explanation:")
    explanation = ""
    if explanation_start:
        for tag in explanation_start.parent.find_next_siblings("p"):
            explanation += tag.get_text(" ", strip=True) + "\n\n"
            if len(explanation) > 1500:
                break

    # Извлекаем URL изображения
    image_tag = soup.find("a", href=True)
    image_url = ""
    if image_tag and image_tag["href"].lower().endswith((".jpg", ".png")):
        image_url = f"https://apod.nasa.gov/apod/{image_tag['href']}"

    return {
        "title": title,
        "credit": credit_text,
        "explanation": explanation.strip(),
        "image_url": image_url,
    }


# 📤 Отправляем пост в канал
async def send_apod_post(context: ContextTypes.DEFAULT_TYPE):
    try:
        apod = fetch_apod_data()
        date_str = datetime.now().strftime("%d %B %Y")

        # 📝 Формируем подпись к изображению
        caption = (
            f"<b>Astronomy Picture of the Day – {date_str}</b>\n\n"
            f"<b>{apod['title']}</b>\n"
            f"<i>Image Credit: {apod['credit']}</i>\n\n"
            f"{apod['explanation']}"
        )

        # Ограничиваем длину подписи до 1024 символов
        if len(caption) > 1024:
            caption = caption[:1020] + "..."

        # Кнопка "Открыть на сайте NASA"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 View on NASA Website", url=APOD_URL)]
        ])

        # Отправка изображения с подписью и кнопкой
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=apod["image_url"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=buttons
        )

        logger.info("Пост успешно опубликован.")

    except Exception as e:
        logger.error(f"Ошибка при отправке поста: {e}")


# 🔘 Обработчик команды /today
async def today(update, context):
    await send_apod_post(context)


# 🚀 Главная функция запуска бота
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Добавляем команду /today
    app.add_handler(CommandHandler("today", today))

    # Планировщик для ежедневного поста в 9:00 по Вильнюсу
    scheduler = AsyncIOScheduler(timezone=timezone("Europe/Vilnius"))
    scheduler.add_job(send_apod_post, trigger="cron", hour=9, minute=0, args=[app.bot])
    scheduler.start()

    logger.info("Бот запущен. Автопост в 09:00 (Europe/Vilnius).")
    app.run_polling()


if __name__ == "__main__":
    main()
