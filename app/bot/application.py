"""Сборка python-telegram-bot Application со всеми обработчиками."""
import logging

from telegram import Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, InlineQueryHandler,
                          MessageHandler, filters)

from app.bot.handlers.callbacks import on_callback
from app.bot.handlers.commands import post, posts, start, stats
from app.bot.handlers.inline import inline_query
from app.bot.handlers.text import text_message

log = logging.getLogger("cgr.bot")

COMMANDS = [("start", "Справка"), ("help", "Справка"), ("stats", "Общая сводка"),
            ("posts", "Все пункты пропуска на сегодня"), ("post", "Один пункт пропуска")]


async def _post_init(application: Application):
    me = await application.bot.get_me()
    if not me.supports_inline_queries:
        log.warning("Инлайн-режим выключен для @%s: включите его в @BotFather командой /setinline", me.username)
    else:
        log.info("Инлайн-режим включён для @%s", me.username)
    await application.bot.set_my_commands(COMMANDS)


async def _on_error(update, context):
    log.error("Ошибка при обработке обновления %s", type(update).__name__, exc_info=context.error)


def build_application(token: str) -> Application:
    # updater(None) не нужен: для polling используем application.updater, для webhook — process_update
    app = Application.builder().token(token).post_init(_post_init).build()
    for name, fn in [("start", start), ("help", start), ("stats", stats), ("posts", posts), ("post", post)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, text_message))
    app.add_error_handler(_on_error)
    return app


ALLOWED_UPDATES = Update.ALL_TYPES
