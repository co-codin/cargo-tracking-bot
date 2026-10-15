"""Команды /start, /help, /stats, /posts, /post."""
import asyncio, html, logging
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import *  # noqa: F401,F403
from app.bot.formatters import COUNTRY_ORDER, country, fmt, footer, free, plural, short, today_icon
from app.bot.keyboards import countries_kb
from app.bot.handlers.common import fail, get_data, lookup


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>Бот статистики CarGoRuqsat</b>\n"
        "Данные об очереди на пунктах пропуска с сайта cgr.qoldau.kz.\n\n"
        "<b>Команды</b>\n"
        "/stats – общая сводка: пользователи, бронирования, оплата в бюджет по годам\n"
        "/posts – свободные места на всех пунктах пропуска\n"
        "/post &lt;название&gt; – один пункт на 14 дней вперёд, например /post Хоргос\n"
        "/post без названия – выбор пункта по стране кнопками\n\n"
        "<b>Поиск</b>\n"
        "Можно просто написать название боту: «хоргос», «дост», «dostyk» – опечатки, латиница "
        "и неправильная раскладка тоже понимаются.\n"
        "В любом чате: наберите @имя_бота и название пункта (инлайн-режим).\n\n"
        "<b>Как читать ответы</b>\n"
        "«34 / 3» – 34 свободных места за 1 МРП и 3 за 100 МРП.\n"
        "🟢 есть места · 🔴 мест нет · ⚪ выходной/закрыто\n"
        "🚫 выходной – пункт не работает, ⏳ – бронирование ещё не открыто.\n"
        "Данные обновляются не чаще раза в 5 минут. Бронировать нужно на сайте, бот только показывает статистику.")
    uname = ctx.bot.username or "имя_бота"
    await update.message.reply_text(text.replace("@имя_бота", "@" + uname), parse_mode=ParseMode.HTML)


async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        d = await get_data()
    except Exception as e:
        return await fail(update, e)
    per = {"За последние 7 дней": "за неделю", "За последний месяц": "за месяц"}

    def line(title, c):
        if not c:
            return None
        return f"{title}: <b>{fmt(c['total'])}</b>  ▲ +{fmt(c['delta'])} {per.get(c['period'], c['period'].lower())}"

    L = ["📊 <b>CarGoRuqsat в цифрах</b>", "", "👥 <b>Пользователи</b>"]
    L += [x for x in (line("Зарегистрировано", d.get("registered_users")),
                      line("С пропусками", d.get("users_with_passes")),
                      line("Бронирований", d.get("total_bookings"))) if x]
    if d["budget_by_year"]:
        L += ["", "💰 <b>Платежи в бюджет</b>"]
        for y, v in d["budget_by_year"].items():
            paid = v["paid_to_budget_kzt"]
            crossed = v["pass_statuses"].get("Пересёк пункт пропуска") or 0
            money = f"<b>{short(paid, '₸')}</b>" if paid else "—"
            word = plural(crossed, 'пересечение', 'пересечения', 'пересечений') if crossed < 1000 else 'пересечений'
            cr = f" · {short(crossed)} {word}" if crossed else ""
            L.append(f"{y}: {money}{cr}")
    if d["registry"]:
        names = {"водителей": "Водители", "владельцев ТС": "Владельцы ТС", "ТС": "Транспорт", "прицепов": "Прицепы"}
        L += ["", "🚛 <b>Реестр</b>"]
        for k, v in d["registry"].items():
            L.append(f"{names.get(k, k)}: {fmt(v['total'])}  ▲ +{fmt(v['last_7_days'])} за неделю")
    L.append(footer(d["updated_at"], d.get("stale")))
    await update.message.reply_text("\n".join(L), parse_mode=ParseMode.HTML)


async def posts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        d = await get_data()
    except Exception as e:
        return await fail(update, e)
    groups = {}
    for p in d["posts"]:
        groups.setdefault(p["country"], []).append(p)
    order = [c for c in COUNTRY_ORDER if c in groups] + [c for c in groups if c not in COUNTRY_ORDER]
    blocks = ["🛃 <b>Пункты пропуска — сегодня</b>\n🟢 есть места · 🔴 мест нет · ⚪ выходной\nСвободно: 1 МРП / 100 МРП"]
    for c in order:
        fl, nm = country(c)
        rows = [f"\n{fl} <b>{nm}</b>"]
        for p in groups[c]:
            t = p["today"]
            val = f"{fmt(free(t, 1))} / {fmt(free(t, 100))}" if t["status"] == "open" else "выходной"
            rows.append(f"{today_icon(p)} {p['name']} — {val}")
        blocks.append("\n".join(rows))
    blocks.append(footer(d["posts_updated_at"], d.get("stale")) + "\nПодробнее: /post &lt;название&gt;")
    chunk = ""
    for b in blocks:
        if len(chunk) + len(b) > 3900:
            await update.effective_message.reply_text(chunk, parse_mode=ParseMode.HTML)
            chunk = ""
        chunk += b + "\n"
    if chunk:
        await update.effective_message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        return await lookup(update, " ".join(ctx.args))
    try:
        d = await get_data()
    except Exception as e:
        return await fail(update, e)
    await update.message.reply_text("🗺 Выберите страну:", reply_markup=countries_kb(d))


