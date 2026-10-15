"""FastAPI-приложение: HTTP API + Telegram-бот (webhook или long polling)."""
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from telegram import Update

from app.api.routes import router
from app.bot.application import ALLOWED_UPDATES, build_application
from app.config import settings

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("cgr.cache").setLevel(settings.cache_log_level)
logging.getLogger("httpx").setLevel(logging.WARNING)  # URL запросов содержит токен — не писать в лог
log = logging.getLogger("cgr.main")

WEBHOOK_PATH = "/telegram/webhook/{secret}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    tg = None
    app.state.bot_mode = "disabled"
    if settings.run_bot and settings.telegram_bot_token:
        tg = build_application(settings.telegram_bot_token.get_secret_value())
        await tg.initialize()
        if tg.post_init:
            await tg.post_init(tg)
        await tg.start()
        if settings.webhook_url:
            url = settings.webhook_url.rstrip("/") + WEBHOOK_PATH.format(secret=settings.webhook_secret)
            await tg.bot.set_webhook(url, allowed_updates=ALLOWED_UPDATES, secret_token=settings.webhook_secret)
            app.state.bot_mode = "webhook"
            log.info("Бот запущен в режиме webhook (%s/telegram/webhook/***)", settings.webhook_url.rstrip("/"))
        else:
            await tg.bot.delete_webhook()
            await tg.updater.start_polling(allowed_updates=ALLOWED_UPDATES)
            app.state.bot_mode = "polling"
            log.info("Бот запущен в режиме long polling")
    else:
        log.warning("TELEGRAM_BOT_TOKEN не задан или RUN_BOT=false — работает только HTTP API")
    app.state.tg = tg
    try:
        yield
    finally:
        if tg:
            if tg.updater and tg.updater.running:
                await tg.updater.stop()
            await tg.stop()
            await tg.shutdown()
            log.info("Бот остановлен")


app = FastAPI(title="CarGoRuqsat stats", lifespan=lifespan)
app.include_router(router)


@app.post(WEBHOOK_PATH, include_in_schema=False)
async def telegram_webhook(secret: str, request: Request):
    tg = request.app.state.tg
    if tg is None or app.state.bot_mode != "webhook" or not hmac.compare_digest(secret, settings.webhook_secret):
        raise HTTPException(status_code=404)
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(header, settings.webhook_secret):
        raise HTTPException(status_code=403)
    await tg.process_update(Update.de_json(await request.json(), tg.bot))
    return {"ok": True}
