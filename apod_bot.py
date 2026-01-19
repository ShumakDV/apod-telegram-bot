import os
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import asyncio

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

APOD_URL = "https://apod.nasa.gov/apod/astropix.html"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ПАРСИНГ APOD ==================

def get_apod_data():
    response = requests.get(APOD_URL, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Заголовок
    title = soup.find_all("b")[0].get_text(strip=True)

    # Image Credit (реальный автор, не NASA)
    credit = "NASA"
    for center in soup.find_all("center"):
        if "Image Credit" in center.text:
            credit = center.text.split("Image Credit:")[-1].strip()
            break

    # Explanation
    explanation = ""
    expl_tag = soup.find("b", string="Explanation:")
    if expl_tag:
        parts = []
        for el in expl_tag.next_siblings:
            if getattr(el, "name", None) == "b":
                break
            if isinstance(el, str):
                text = el.strip()
                if text:
                    parts.append(text)
        explanation = " ".join(parts)

    # Картинка (оригинал)
    image_url = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith((".jpg", ".jpeg", ".png")):
            image_url = "https://apod.nasa.gov/apod/" + href
            break

    if not image_url:
        raise RuntimeError("Не удалось найти изображение APOD")

    # Ссылка на сегодняшний пост
    today = datetime.now(timezone.utc)
    page_url = f"https://apod.nasa.gov/apod/ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "explanation": explanation,
        "image_url": image_url,
        "page_url": page_url,
    }

# ================== ОТПРАВКА В КАНАЛ ==================

async def send_to_channel():
    data = get_apod_data()

    caption = (
        f"*Astronomy Picture of the Day – {datetime.now(timezone.utc).strftime('%d %B %Y')}*\n\n"
        f"*{data['title']}*\n"
        f"_Image Credit: {data['credit']}_\n\n"
        f"{data['explanation']}"
    )

    # Ограничение Telegram
    if len(caption) > 1024:
        caption = caption[:1020] + "..."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]
    ])

    bot = Bot(token=BOT_TOKEN)

    await bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=data["image_url"],
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

    logger.info("✅ Пост успешно отправлен в канал")

# ================== ЗАПУСК ==================

if __name__ == "__main__":
    asyncio.run(send_to_channel())
