"""Общие функции обработчиков."""
import asyncio, html, logging
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import card_text, country, pidx
from app.bot.keyboards import card_kb
from app.services import cache, matching


async def get_data():
    return await asyncio.to_thread(cache.fetch)


async def fail(update, e):
    logging.exception("fetch failed")
    if update.effective_message is None:
        return
    await update.effective_message.reply_text("⚠️ Не удалось получить данные с сайта cgr.qoldau.kz. Попробуйте позже.")


async def lookup(update: Update, query: str):
    if update.effective_message is None:
        return
    try:
        d = await get_data()
    except Exception as e:
        return await fail(update, e)
    kind, res, corrected = matching.resolve(d["posts"], query)
    msg = update.effective_message
    if kind == "one":
        return await msg.reply_text(card_text(d, res, corrected), parse_mode=ParseMode.HTML,
                                    reply_markup=card_kb(pidx(d, res)))
    if kind == "many":
        kb = [[Btn(f"{country(p['country'])[0]} {p['name']}"[:64], callback_data=f"p:{pidx(d, p)}")] for p in res]
        return await msg.reply_text("Возможно, вы имели в виду:", reply_markup=InlineKeyboardMarkup(kb))
    await msg.reply_text(f"🤷 Пункт пропуска «{html.escape(query)}» не найден.\n"
                         "Проверьте название или выберите из списка.", parse_mode=ParseMode.HTML,
                         reply_markup=InlineKeyboardMarkup([[Btn("🗺 Выбрать по стране", callback_data="countries")],
                                                            [Btn("📋 Все пункты", callback_data="all")]]))


