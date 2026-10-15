"""Telegram-бот со статистикой CarGoRuqsat (python-telegram-bot v21)."""
import asyncio, difflib, logging, os
from datetime import date
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
import parser as cgr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # не писать токен в лог


def fmt(n):
    return "—" if n is None else f"{n:,}".replace(",", " ")


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


def short(n, unit=""):
    """29186988744 -> '29,2 млрд', 1579204 -> '1,58 млн'."""
    for v, w in ((1e9, "млрд"), (1e6, "млн"), (1e3, "тыс.")):
        if abs(n) >= v:
            x = n / v
            s = f"{x:.2f}" if x < 10 else f"{x:.1f}" if x < 100 else f"{x:.0f}"
            s = s.rstrip("0").rstrip(".").replace(".", ",")
            return f"{s} {w}" + (f" {unit}" if unit else "")
    return fmt(n) + (f" {unit}" if unit else "")


MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7,
          "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def day_date(label):
    try:
        d, m = label.split()
        today = date.today()
        dt = date(today.year, MONTHS[m[:3]], int(d))
        if (dt - today).days < -180:
            dt = dt.replace(year=today.year + 1)
        return dt
    except Exception:
        return None


def day_label(day):
    dt = day_date(day["date"] or "")
    return f"{day['date']} ({WD[dt.weekday()]})" if dt else (day["date"] or "?")


COUNTRIES = {"CN": ("🇨🇳", "Китай"), "UZ": ("🇺🇿", "Узбекистан"), "KG": ("🇰🇬", "Кыргызстан"),
             "RU": ("🇷🇺", "Россия"), "TM": ("🇹🇲", "Туркменистан"), "XA": ("🚢", "Морской порт")}
COUNTRY_ORDER = ["CN", "UZ", "KG", "TM", "XA", "RU"]


def country(code):
    return COUNTRIES.get(code, ("🏳", code or "Другое"))


def free(day, k):
    return day.get("free", {}).get(k, 0) if day["status"] == "open" else 0


def day_state(day):
    if day["status"] == "day_off":
        return "🚫 выходной"
    if day["status"] == "not_open":
        return "⏳ бронь не открыта"
    a, b = free(day, 1), free(day, 100)
    return "мест нет" if a == 0 and b == 0 else f"{fmt(a)} / {fmt(b)}"


def footer(ts):
    return f"\n<i>🕒 Обновлено: {ts} (время KZ) · cgr.qoldau.kz</i>"


async def get_data():
    return await asyncio.to_thread(cgr.fetch)


async def fail(update, e):
    logging.exception("fetch failed")
    await update.message.reply_text("⚠️ Не удалось получить данные с сайта cgr.qoldau.kz. Попробуйте позже.")


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Бот статистики CarGoRuqsat</b>\n"
        "Данные об очереди на пунктах пропуска с сайта cgr.qoldau.kz.\n\n"
        "<b>Команды</b>\n"
        "/stats – общая сводка: пользователи, бронирования, оплата в бюджет по годам\n"
        "/posts – свободные места на всех пунктах пропуска\n"
        "/post &lt;название&gt; – один пункт на 14 дней вперёд, например /post Хоргос "
        "(можно частично и с опечаткой)\n\n"
        "<b>Как читать ответы</b>\n"
        "«34 / 3» – 34 свободных места за 1 МРП и 3 за 100 МРП.\n"
        "🟢 есть места · 🔴 мест нет · ⚪ выходной/закрыто\n"
        "🚫 выходной – пункт не работает, ⏳ – бронирование ещё не открыто.\n"
        "Данные обновляются не чаще раза в 5 минут. Бронировать нужно на сайте, бот только показывает статистику.",
        parse_mode=ParseMode.HTML)


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
    L.append(footer(d["updated_at"]))
    await update.message.reply_text("\n".join(L), parse_mode=ParseMode.HTML)


def today_icon(p):
    t = p["today"]
    if t["status"] != "open":
        return "⚪"
    return "🟢" if free(t, 1) or free(t, 100) else "🔴"


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
    blocks.append(footer(d["posts_updated_at"]) + "\nПодробнее: /post &lt;название&gt;")
    chunk = ""
    for b in blocks:
        if len(chunk) + len(b) > 3900:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            chunk = ""
        chunk += b + "\n"
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


def render_post(p, updated):
    fl, nm = country(p["country"])
    t = p["today"]
    L = [f"🛃 <b>{p['name']}</b>", f"{fl} {nm}", "", f"<b>Сегодня, {day_label(t)}</b>"]
    if t["status"] == "open":
        for k in (1, 100):
            n = free(t, k)
            L.append(f"{'✅' if n else '❌'} {k} МРП: {fmt(n) if n else 'мест нет'}")
    else:
        L.append(day_state(t))
    L += ["", "<b>Ближайшее свободное</b>"]
    for k in (1, 100):
        first = next((x for x in p["days"] if free(x, k)), None)
        L.append(f"{k} МРП: {day_label(first) + ' — ' + fmt(free(first, k)) + ' ' + plural(free(first, k), 'место', 'места', 'мест') if first else 'нет'}")
    L += ["", "<b>Ближайшие дни</b> (1 МРП / 100 МРП)"]
    days = [x for x in p["days"] if x["status"] != "not_open"][:21]
    groups = []
    for x in days:
        st = day_state(x)
        if groups and groups[-1][2] == st:
            groups[-1][1] = x
        else:
            groups.append([x, x, st])
    for a, b, st in groups:
        if a is b:
            lbl = day_label(a)
        else:
            da, db = a["date"].split(), b["date"].split()
            lbl = f"{da[0]}–{b['date']}" if da[1] == db[1] else f"{a['date']} – {b['date']}"
        L.append(f"{lbl}: {st}")
    ft, n = p["free_total"], p["open_days"]
    L += ["", f"Всего: <b>{fmt(ft[1])} / {fmt(ft[100])}</b> мест "
              f"за {n} {plural(n, 'день', 'дня', 'дней')}"]
    L.append(footer(updated))
    return "\n".join(L)


async def post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await update.message.reply_text("Использование: /post &lt;название&gt;\nНапример: /post Хоргос", parse_mode=ParseMode.HTML)
    try:
        d = await get_data()
    except Exception as e:
        return await fail(update, e)
    p = find_post(d["posts"], " ".join(ctx.args))
    if not p:
        return await update.message.reply_text("🤷 Пункт пропуска не найден. Список всех пунктов: /posts")
    await update.message.reply_text(render_post(p, d["posts_updated_at"]), parse_mode=ParseMode.HTML)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Задайте переменную окружения TELEGRAM_BOT_TOKEN")
    async def post_init(application):
        await application.bot.set_my_commands([
            ("start", "Справка"), ("stats", "Общая сводка"),
            ("posts", "Загруженность пунктов пропуска"), ("post", "Один пункт пропуска"),
        ])
    app = Application.builder().token(token).post_init(post_init).build()
    for name, fn in [("start", start), ("help", start), ("stats", stats), ("posts", posts), ("post", post)]:
        app.add_handler(CommandHandler(name, fn))
    app.run_polling()


if __name__ == "__main__":
    main()
