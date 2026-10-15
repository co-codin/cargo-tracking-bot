"""Обычный текст в личном чате = /post <текст>."""
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers.common import lookup


async def text_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None:
        return
    q = (msg.text or "").strip()
    if q:
        await lookup(update, q[:100])


