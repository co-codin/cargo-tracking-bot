"""Инлайн-режим: @бот название."""
import asyncio, html, logging
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import card_text, country, day_state, fmt, free, pidx
from app.bot.handlers.common import get_data
from app.services import matching


async def inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.inline_query.query.strip()
    try:
        d = await get_data()
    except Exception:
        logging.exception("fetch failed")
        return await update.inline_query.answer([], cache_time=10)
    found = [r[0] for r in matching.search(d["posts"], q, limit=20)] if q else d["posts"][:50]
    results = []
    for p in found:
        t = p["today"]
        if t["status"] == "open":
            desc = f"Сегодня свободно: 1 МРП – {fmt(free(t, 1))}, 100 МРП – {fmt(free(t, 100))}"
        else:
            desc = "Сегодня " + day_state(t).replace("🚫 ", "")
        fl, nm = country(p["country"])
        results.append(InlineQueryResultArticle(
            id=str(pidx(d, p)), title=f"{fl} {p['name']}", description=desc,
            input_message_content=InputTextMessageContent(card_text(d, p), parse_mode=ParseMode.HTML)))
    await update.inline_query.answer(results, cache_time=60)


