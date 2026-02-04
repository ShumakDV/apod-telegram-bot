import os
import logging
import re
from datetime import datetime, timezone, time as dtime
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from pytz import timezone as tz
from PIL import Image

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

APOD_URL = "https://apod.nasa.gov/apod/astropix.html"
BASE_URL = "https://apod.nasa.gov/apod/"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ВСПОМОГАТЕЛЬНЫЕ ==================

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _abs_apod_url(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return BASE_URL + href.lstrip("./")


def _pick_best_image_url(soup: BeautifulSoup) -> str | None:
    candidates = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if low.endswith((".jpg", ".jpeg", ".png")):
            abs_url = _abs_apod_url(href)
            score = 0
            if "/image/" in abs_url.lower() or "image/" in low:
                score += 10
            score += min(len(abs_url), 200) / 200
            candidates.append((score, abs_url))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    img = soup.find("img")
    if img and img.get("src"):
        src = img["src"].strip()
        if src.lower().endswith((".jpg", ".jpeg", ".png")):
            return _abs_apod_url(src)

    return None


def download_image(url: str) -> BytesIO | None:
    """
    СТАБИЛЬНО:
    - скачиваем файл сами
    - проверяем Content-Type
    - Telegram получает готовый image/*
    - нормализуем размеры (фикс Photo_invalid_dimensions)
    """
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        content_type = r.headers.get("Content-Type", "").lower()
        if not content_type.startswith("image/"):
            logger.error(f"APOD returned non-image content: {content_type}")
            return None

        src = BytesIO(r.content)
        src.seek(0)

        img = Image.open(src)
        img.load()

        w, h = img.size
        if w <= 0 or h <= 0:
            logger.error(f"Invalid image size: {w}x{h}")
            return None

        MAX_SIDE = 10000
        if max(w, h) > MAX_SIDE:
            scale = MAX_SIDE / max(w, h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = img.resize((new_w, new_h), Image.LANCZOS)

        if img.mode != "RGB":
            img = img.convert("RGB")

        out = BytesIO()
        out.name = "apod.jpg"
        img.save(out, format="JPEG", quality=92, optimize=True)
        out.seek(0)
        return out

    except Exception as e:
        logger.error(f"Failed to download APOD image: {e}")
        return None

# ================== ПАРСИНГ APOD ==================

def get_apod_data():
    response = requests.get(APOD_URL, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # ---------- Заголовок ----------
    title = "Astronomy Picture of the Day"
    b_tags = soup.find_all("b")
    if b_tags:
        t = b_tags[0].get_text(strip=True)
        if t:
            title = t

    # ---------- Image Credit ----------
    credit = "NASA"
    for center in soup.find_all("center"):
        text = center.get_text(" ", strip=True)
        if "Image Credit" in text:
            raw = text.split("Image Credit")[-1]
            raw = raw.replace(":", "")
            raw = _clean_text(raw)
            if raw:
                credit = raw
            break

    # ---------- Explanation (3–4 предложения) ----------
    explanation_text = ""
    expl_b = soup.find("b", string=re.compile(r"^\s*Explanation:\s*$"))
    if expl_b:
        parts = []
        for sib in expl_b.next_siblings:
            if getattr(sib, "name", None) == "b":
                break
            if isinstance(sib, str):
                if sib.strip():
                    parts.append(sib.strip())
            else:
                txt = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else ""
                if txt:
                    parts.append(txt)

        explanation_text = _clean_text(" ".join(parts))

    short_explanation = ""
    if explanation_text:
        sentences = re.split(r"(?<=\.)\s+", explanation_text)
        short_explanation = " ".join(sentences[:4]).strip()
        if short_explanation and not short_explanation.endswith("."):
            short_explanation += "."

    # ---------- Картинка ----------
    image_url = _pick_best_image_url(soup)

    # ---------- Ссылка на страницу ----------
    today = datetime.now(timezone.utc)
    page_url = f"{BASE_URL}ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "image_url": image_url,
        "page_url": page_url,
        "short_explanation": short_explanation,
    }

# ================== ПОДПИСЬ ==================

def build_caption(data):
    now = datetime.now(timezone.utc).astimezone(tz("Europe/Vilnius"))

    caption = (
        f"<b>Astronomy Picture of the Day – {now.strftime('%d %B %Y')}</b>\n\n"
        f"<b>{data.get('title')}</b>\n"
        f"<i>Image Credit: {data.get('credit')}</i>\n\n"
        f"{data.get('short_explanation')}"
    )

    if len(caption) > 1024:
        caption = caption[:1020] + "..."

    return caption

# ================== ОТПРАВКА ==================

async def send_apod(chat_id: str, bot):
    data = get_apod_data()
    caption = build_caption(data)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]]
    )

    image_url = data.get("image_url")

    # Нет картинки
    if not image_url:
        await bot.send_message(
            chat_id=chat_id,
            text=f"Сегодня на APOD не картинка 😅\n{data['page_url']}",
            reply_markup=keyboard,
        )
        return

    image_file = download_image(image_url)
    if not image_file:
        await bot.send_message(
            chat_id=chat_id,
            text=f"Не удалось загрузить изображение.\n{data['page_url']}",
            reply_markup=keyboard,
        )
        return

    await bot.send_photo(
        chat_id=chat_id,
        photo=InputFile(image_file),
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

# ================== /today ==================

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_apod(update.effective_chat.id, context.bot)

# ================== АВТОПОСТ ==================

async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    if not CHANNEL_ID:
        logger.error("CHANNEL_ID is not set")
        return

    await send_apod(CHANNEL_ID, context.bot)
    logger.info("✅ Автопост отправлен")

# ================== ЗАПУСК ==================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("today", today))

    vilnius_tz = tz("Europe/Vilnius")
    app.job_queue.run_daily(
        daily_post,
        time=dtime(hour=9, minute=0, tzinfo=vilnius_tz),
    )

    logger.info("✅ Бот запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
