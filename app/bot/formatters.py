"""Текст ответов бота (HTML)."""
import html
from datetime import date


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
            if "." in s:
                s = s.rstrip("0").rstrip(".")
            s = s.replace(".", ",")
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


def footer(ts, stale=False):
    note = ("\n⚠️ <i>Сайт сейчас недоступен — показаны последние сохранённые данные, "
            "они могут быть устаревшими.</i>") if stale else ""
    return note + f"\n<i>🕒 Обновлено: {ts} (время KZ) · cgr.qoldau.kz</i>"


def today_icon(p):
    t = p["today"]
    if t["status"] != "open":
        return "⚪"
    return "🟢" if free(t, 1) or free(t, 100) else "🔴"


def render_post(p, updated, stale=False):
    fl, nm = country(p["country"])
    t = p["today"]
    L = [f"🛃 <b>{html.escape(p['name'])}</b>", f"{fl} {html.escape(nm)}", "", f"<b>Сегодня, {day_label(t)}</b>"]
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
    L.append(footer(updated, stale))
    return "\n".join(L)


def pidx(d, p):
    return d["posts"].index(p)


def card_text(d, p, corrected=False):
    t = render_post(p, d["posts_updated_at"], d.get("stale"))
    if corrected:
        t = f"🔎 Показано: {html.escape(p['name'].replace(' - ', ' — '))}\n\n" + t
    return t




def delta(n):
    """+5 / −5 / 0 (без «+-»)."""
    if n is None:
        return "—"
    if n < 0:
        return "▼ −" + fmt(-n)
    return "▲ +" + fmt(n)


def split_chunks(blocks, limit=4096):
    """Склеивает блоки в сообщения ≤ limit символов, режет только по строкам."""
    lines = []
    for b in blocks:
        lines += b.split("\n")
    out, cur = [], ""
    for ln in lines:
        while len(ln) > limit:  # аварийно: строка длиннее лимита
            if cur:
                out.append(cur); cur = ""
            out.append(ln[:limit]); ln = ln[limit:]
        cand = ln if not cur else cur + "\n" + ln
        if len(cand) > limit:
            out.append(cur); cur = ln
        else:
            cur = cand
    if cur.strip():
        out.append(cur)
    return [c for c in out if c.strip()]
