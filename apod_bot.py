import os
import logging
import re
from html import escape
from datetime import datetime, timezone, time

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


def get_apod_data():
    response = requests.get(APOD_URL, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # ---------- Заголовок ----------
    # На APOD заголовок обычно в первом <b>, но иногда страница меняется.
    title = "Astronomy Picture of the Day"
    b_tags = soup.find_all("b")
    if b_tags:
        title = b_tags[0].get_text(strip=True) or title

    # ---------- Image Credit ----------
    credit = "NASA"
    for center in soup.find_all("center"):
        text = center.get_text(" ", strip=True)
        if "Image Credit" in text:
            # Иногда бывает "Image Credit & Copyright:" и т.п.
            credit = text.split("Image Credit")[-1]
            credit = credit.replace(":", "").replace("& Copyright", "").strip()
            if credit:
                break
            credit = "NASA"

    # ---------- Explanation ----------
    explanation_text = ""
    expl_b = soup.find("b", string=re.compile(r"^\s*Explanation:\s*$"))
    if expl_b:
        parts = []
        for sib in expl_b.next_siblings:
            # Останавливаемся, когда пошёл следующий жирный заголовок
            if getattr(sib, "name", None) == "b":
                break
            # Текстовые узлы
            if isinstance(sib, str):
                cleaned = sib.strip()
                if cleaned:
                    parts.append(cleaned)
            else:
                # Иногда рядом бывают теги <p>, <br> и т.п.
                txt = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else ""
                if txt:
                    parts.append(txt)

        explanation_text = " ".join(parts)

    explanation_text = re.sub(r"\s+", " ", explanation_text).strip()

    # ---------- Берём первые 2–3 предложения ----------
    short_explanation = ""
    if explanation_text:
        sentences = re.split(r"(?<=\.)\s+", explanation_text)
        short_explanation = " ".join(sentences[:3]).strip()
        if short_explanation and not short_explanation.endswith("."):
            short_explanation += "."

    # ---------- Оригинальная картинка ----------
    image_url = None

    # Сначала пробуем найти <img src="image/...jpg"> — часто самый надёжный путь
    img = soup.find("img")
    if img and img.get("src"):
        src = img["src"].strip()
        if src.lower().endswith((".jpg", ".jpeg", ".png")):
            image_url = "https://apod.nasa.gov/apod/" + src.lstrip("./")

    # Если не нашли — ищем ссылку на jpg/png в <a href=...>
    if not image_url:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            low = href.lower()
            if low.endswith((".jpg", ".jpeg", ".png")):
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


# ================== СБОРКА ТЕКСТА ==================


def build_caption_and_text(data):
    now = datetime.now(timezone.utc).astimezone(tz("Europe/Vilnius"))
    date_str = now.strftime("%d %B %Y")

    # ВАЖНО:
    # - caption у фото в Telegram ограничен 1024 символами
    # - полный текст лучше отправлять отдельным сообщением (лимит 4096)
    caption = (
        f"<b>Astronomy Picture of the Day — {escape(date_str)}</b>\n\n"
        f"<b>{escape(data['title'])}</b>\n"
        f"<i>Image Credit: {escape(data['credit'])}</i>"
    )
    if len(caption) > 1024:
        caption = caption[:1020] + "..."

    # Полный текст поста (можешь заменить short_explanation на explanation_text,
    # если решишь парсить полный текст)
    explanation = data.get("short_explanation") or "Описание сегодня недоступно на странице APOD."

    post_text = (
        f"<b>{escape(data['title'])}</b>\n"
        f"<i>Image Credit: {escape(data['credit'])}</i>\n\n"
        f"{escape(explanation)}\n\n"
        f"🌐 {escape(data['page_url'])}"
    )
    if len(post_text) > 4096:
        post_text = post_text[:4090] + "..."

    return caption, post_text


# ================== ОТПРАВКА ==================


async def send_apod(chat_id: str, bot):
    data = get_apod_data()
    caption, post_text = build_caption_and_text(data)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌐 View on NASA Website", url=data["page_url"])]]
    )

    # Если сегодня не картинка (бывает видео) — просто отправим текст + ссылку
    if not data["image_url"]:
        await bot.send_message(
            chat_id=chat_id,
            text=post_text,
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=keyboard,
        )
        return

    # 1) Фото с короткой подписью
    await bot.send_photo(
        chat_id=chat_id,
        photo=data["image_url"],
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # 2) Отдельным сообщением — текст (чтобы был “как пост”)
    await bot.send_message(
        chat_id=chat_id,
        text=post_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
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

    # /today — в личку
    app.add_handler(CommandHandler("today", today))

    # автопост в 09:00 Вильнюс
    vilnius_tz = tz("Europe/Vilnius")
    app.job_queue.run_daily(
        daily_post,
        time=time(hour=9, minute=0, tzinfo=vilnius_tz),
        name="daily_post",
    )

    logger.info("✅ Бот запущен. /today — в личку, автопост — в канал.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
