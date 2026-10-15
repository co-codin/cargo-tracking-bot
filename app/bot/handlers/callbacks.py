"""Нажатия инлайн-кнопок."""
import asyncio, html, logging
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import card_text, country
from app.bot.keyboards import card_kb, countries_kb, country_posts_kb
from app.bot.handlers.commands import posts
from app.services import cache


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if cq is None:
        return
    data = cq.data or ""
    valid = data in ("all", "countries") or data.startswith("c:") or (data[:2] in ("p:", "r:") and data[2:].isdigit())
    if not valid:
        return await cq.answer("Кнопка устарела, откройте меню заново")
    try:
        d = await asyncio.to_thread(cache.fetch, data.startswith("r:"))
    except Exception:
        logging.exception("fetch failed")
        return await cq.answer("⚠️ Сайт недоступен, попробуйте позже", show_alert=True)
    try:
        if data == "all":
            await cq.answer()
            return await posts(update, ctx)
        if data == "countries":
            await cq.answer()
            return await cq.edit_message_text("🗺 Выберите страну:", reply_markup=countries_kb(d))
        if data.startswith("c:"):
            code = data[2:]
            fl, nm = country(code)
            await cq.answer()
            return await cq.edit_message_text(f"{fl} <b>{html.escape(nm)}</b> — выберите пункт пропуска:\n🟢 есть места сегодня · 🔴 нет · ⚪ выходной",
                                              parse_mode=ParseMode.HTML, reply_markup=country_posts_kb(d, code))
        if data[:2] in ("p:", "r:"):
            i = int(data[2:])
            if not 0 <= i < len(d["posts"]):
                return await cq.answer("Список пунктов изменился, откройте его заново", show_alert=True)
            p = d["posts"][i]
            text = card_text(d, p)
            if data.startswith("r:"):
                await cq.answer("Обновлено")
                if cq.message and cq.message.text_html == text:
                    return
                return await cq.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=card_kb(i))
            await cq.answer()
            if cq.message is None:
                return
            return await cq.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=card_kb(i))
        await cq.answer()
    except Exception as e:
        if "not modified" in str(e).lower():
            return
        raise


