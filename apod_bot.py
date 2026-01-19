import os
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен и канал из переменных среды (Railway)
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Основная функция получения данных с сайта NASA APOD
def get_apod_data():
    url = "https://apod.nasa.gov/apod/astropix.html"
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Заголовок (в первом <b>)
    title = soup.find_all("b")[0].text.strip()

    # Автор (ищем текст "Image Credit")
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

    # Ссылка на полное изображение
    image_tag = soup.find("a", href=True)
    image_url = f"https://apod.nasa.gov/apod/{image_tag['href']}" if image_tag else None

    # Ссылка на текущий пост
    today = datetime.utcnow()
    page_url = f"https://apod.nasa.gov/apod/ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "explanation": explanation,
        "image_url": image_url,
        "page_url": page_url
    }

# Функция отправки поста в канал
def send_apod_to_channel():
    data = get_apod_data()

    caption = (
        f"*Astronomy Picture of the Day – {datetime.utcnow().strftime('%d %B %Y')}*\n\n"
        f"*{data['title']}*\n"
        f"_Image Credit: {data['credit']}_\n\n"
        f"{data['explanation']}"
    )

    button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]
    ])

    bot = Bot(token=BOT_TOKEN)

    try:
        bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=data["image_url"],
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=button
        )
        logger.info("✅ Пост успешно отправлен.")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке поста: {e}")

# Запуск
if __name__ == "__main__":
    send_apod_to_channel()
