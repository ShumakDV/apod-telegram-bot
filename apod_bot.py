import os
import logging
import re
from datetime import datetime, timezone, time as dtime

import requests
from bs4 import BeautifulSoup
from pytz import timezone as tz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

APOD_URL = "https://apod.nasa.gov/apod/astropix.html"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ПАРСИНГ APOD ==================


def _clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s


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
            # бывает "Image Credit & Copyright:"
            credit = text.split("Image Credit")[-1]
            credit = credit.replace(":", "").strip()
            credit = _clean_text(credit)
            if credit:
                break
            credit = "NASA"

    # ---------- Explanation (берём 3-4 предложения) ----------
    explanation_text = ""
    expl_b = soup.find("b", string=re.compile(r"^\s*Explanation:\s*$"))
    if expl_b:
        parts = []
        for sib in expl_b.next_siblings:
            # стоп, когда пошёл следующий жирный заголовок
            if getattr(sib, "name", None) == "b":
                break

            if isinstance(sib, str):
                cleaned = sib.strip()
                if cleaned:
                    parts.append(cleaned)
            else:
                # иногда это <p>, <br> и т.п.
                txt = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else ""
                if txt:
                    parts.append(txt)

        explanation_text = _clean_text(" ".join(parts))

    # 3–4 предложения
    short_explanation = ""
    if explanation_text:
        sentences = re.split(r"(?<=\.)\s+", explanation_text)
        short_explanation = " ".join(sentences[:4]).strip()
        if short_explanation and not short_explanation.endswith("."):
            short_explanation += "."

    # ---------- Оригинальная картинка ----------
    image_url = None

    # часто самый надёжный путь — <img src="image/...jpg">
    img = soup.find("img")
    if img and img.get("src"):
        src = img["src"].strip()
        if src.lower().endswith((".jpg", ".jpeg", ".png")):
            image_url = "https://apod.nasa.gov/apod/" + src.lstrip("./")

    # запасной вариант — ссылка <a href="image/...jpg">
    if not image_url:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().endswith((".jpg", ".jpeg", ".png")):
                image_url = "https://apod.nasa.gov/apod/" + href.lstrip("./")
                break

    # ---------- Ссылка на страницу ----------
    today = datetime.now(timezone.utc)
    page_url = f"https://apod.nasa.gov/apod/ap{today.strftime('%y%m%d')}.html"

    return {
        "title": title,
        "credit": credit,
        "image_url": image_url,
        "page_url": page_url,
        "short_explanation": short_explanation,
    }


# ================== СБОРКА ПОДПИСИ (ОДНО СООБЩЕНИЕ) ==================


def build_caption(data):
    now = datetime.now(timezone.utc).astimezone(tz("Europe/Vilnius"))

    # Markdown часто ломается на символах _, (), [], поэтому используем HTML-режим
    title = data.get("title") or "Astronomy Picture of the Day"
    credit = data.get("credit") or "NASA"
    expl = data.get("short_explanation") or "Описание сегодня недоступно на странице APOD."

    caption = (
        f"<b>Astronomy Picture of the Day – {now.strftime('%d %B %Y')}</b>\n\n"
        f"<b>{title}</b>\n"
        f"<i>Image Credit: {credit}</i>\n\n"
        f"{expl}"
    )

    # лимит Telegram для caption у фото
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

    # Если сегодня не картинка (бывает видео), фото не отправим — иначе будет ошибка.
    # Но ты просил ОДНО сообщение с фото+текстом — значит, в такой день отправим просто сообщение со ссылкой.
    if not data["image_url"]:
        await bot.send_message(
            chat_id=chat_id,
            text=f"Сегодня на APOD не картинка 😅\n{data['page_url']}",
            reply_markup=keyboard,
            disable_web_page_preview=False,
        )
        return

    await bot.send_photo(
        chat_id=chat_id,
        photo=data["image_url"],
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
    logger.info("✅ Автопост отправлен в канал")


# ================== ЗАПУСК ==================


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("today", today))

    # автопост в 09:00 Вильнюс
    vilnius_tz = tz("Europe/Vilnius")
    app.job_queue.run_daily(
        daily_post,
        time=dtime(hour=9, minute=0, tzinfo=vilnius_tz),
        name="daily_post",
    )

    logger.info("✅ Бот запущен. /today — в личку, автопост — в канал.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
