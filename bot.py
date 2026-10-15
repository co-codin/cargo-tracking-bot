"""Telegram bot serving CarGoRuqsat statistics (python-telegram-bot v21)."""
import asyncio, difflib, logging, os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
import parser as cgr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
FLAGS = {"CN": "🇨🇳", "UZ": "🇺🇿", "KG": "🇰🇬", "RU": "🇷🇺", "TM": "🇹🇲", "AZ": "🇦🇿"}


def fmt(n):
    return "—" if n is None else f"{n:,}".replace(",", " ")


async def get_data():
    return await asyncio.to_thread(cgr.fetch)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "CarGoRuqsat statistics bot (cgr.qoldau.kz)\n\n"
        "/stats – summary\n/posts – load of all border crossings\n"
        "/post <name> – one crossing (e.g. /post Хоргос)\n\nData is cached for 5 minutes.")


async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        d = await get_data()
    except Exception as e:
        logging.exception("fetch failed")
        return await update.message.reply_text(f"Failed to fetch data: {e}")
    L = [f"<b>CarGoRuqsat в цифрах</b>\nАктуально на: {d['updated_at']}", ""]
    for key, title in [("registered_users", "Зарегистрировано пользователей"),
                       ("total_bookings", "Всего бронирований"),
                       ("users_with_passes", "Пользователи с пропусками")]:
        c = d.get(key)
        if c:
            L.append(f"{title}: <b>{fmt(c['total'])}</b> (+{fmt(c['delta'])} {c['period'].lower()})")
    if d["budget_by_year"]:
        L += ["", "<b>Оплачено за пропуск в бюджет:</b>"]
        for y, v in d["budget_by_year"].items():
            crossed = v["pass_statuses"].get("Пересёк пункт пропуска")
            L.append(f"{y}: {fmt(v['paid_to_budget_kzt'])} ₸ (пересекли: {fmt(crossed)})")
    if d["registry"]:
        L += ["", "<b>Реестр (за 7 дней):</b>"]
        for k, v in d["registry"].items():
            L.append(f"{k}: {fmt(v['total'])} (+{fmt(v['last_7_days'])})")
    await update.message.reply_text("\n".join(L), parse_mode=ParseMode.HTML)


def post_line(p):
    t = p["today"]
    if t["status"] == "open":
        today = f"сегодня 1 МРП: {t['free'].get(1, 0)}, 100 МРП: {t['free'].get(100, 0)}"
    else:
        today = {"day_off": "сегодня выходной", "not_open": "сегодня не открыто"}.get(t["status"], t["status"])
    ft = p["free_total"]
    return (f"{FLAGS.get(p['country'], '')} <b>{p['name']}</b>: {today}; "
            f"всего свободно {ft[1]} / {ft[100]} за {p['open_days']} дн.")


async def posts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        d = await get_data()
    except Exception as e:
        return await update.message.reply_text(f"Failed to fetch data: {e}")
    head = f"<b>Загруженность постов</b> (свободно 1 МРП / 100 МРП)\nАктуально на: {d['posts_updated_at']}\n"
    chunk = head
    for p in d["posts"]:
        line = post_line(p) + "\n"
        if len(chunk) + len(line) > 3900:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            chunk = ""
        chunk += line
    if chunk:
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


def find_post(posts_, q):
    q = q.lower().strip()
    sub = [p for p in posts_ if q in p["name"].lower()]
    if sub:
        return sub[0]
    names = {}
    for p in posts_:
        names[p["name"].lower()] = p
        for part in p["name"].lower().split(" - "):
            names[part.strip()] = p
    m = difflib.get_close_matches(q, list(names), n=1, cutoff=0.5)
    return names[m[0]] if m else None


async def post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await update.message.reply_text("Usage: /post <name>, e.g. /post Достык")
    try:
        d = await get_data()
    except Exception as e:
        return await update.message.reply_text(f"Failed to fetch data: {e}")
    p = find_post(d["posts"], " ".join(ctx.args))
    if not p:
        return await update.message.reply_text("Crossing not found. See /posts for the list.")
    L = [post_line(p), "", "Ближайшие дни (свободно 1 МРП / 100 МРП):"]
    for day in p["days"][:14]:
        if day["status"] == "open":
            L.append(f"{day['date']}: {day['free'].get(1, 0)} / {day['free'].get(100, 0)}")
        else:
            L.append(f"{day['date']}: {'выходной' if day['status']=='day_off' else 'не открыто'}")
    await update.message.reply_text("\n".join(L), parse_mode=ParseMode.HTML)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN environment variable")
    app = Application.builder().token(token).build()
    for name, fn in [("start", start), ("help", start), ("stats", stats), ("posts", posts), ("post", post)]:
        app.add_handler(CommandHandler(name, fn))
    app.run_polling()


if __name__ == "__main__":
    main()
