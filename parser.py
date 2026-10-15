"""Parser for https://cgr.qoldau.kz/ru/information/stat (server-rendered HTML)."""
import json, re, sys, time
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

URL = "https://cgr.qoldau.kz/ru/information/stat"
CACHE_TTL = 300
_cache = {"t": 0.0, "data": None}
KZ_TZ = timezone(timedelta(hours=5))


def _num(s):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else None


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _chart(div):
    try:
        return json.loads(div.get("data-chart-options", "{}"))
    except ValueError:
        return {}


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    text = _clean(soup.get_text(" "))
    out = {}
    m = re.search(r"Актуально на:\s*(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", text)
    out["updated_at"] = m.group(1) if m else None

    def card(label):
        m = re.search(re.escape(label) + r"\s+([\d ]+?)\s+(\d+)\s+(За (?:последние 7 дней|последний месяц))", text)
        if not m:
            return None
        return {"total": _num(m.group(1)), "delta": int(m.group(2)), "period": m.group(3)}

    out["registered_users"] = card("Зарегистрировано пользователей")
    out["total_bookings"] = card("Всего бронирований")
    out["users_with_passes"] = card("Пользователи с пропусками")

    # Per-year pass data: tab links -> panes
    years = {}
    for a in soup.select(".nav-pills a[href^='#page_']"):
        year = _clean(a.get_text())
        pane = soup.find(id=a["href"][1:])
        if not pane:
            continue
        ptxt = _clean(pane.get_text(" "))
        pm = re.search(r"Оплачено за пропуск в бюджет:\s*([\d ]+)", ptxt)
        y = {"paid_to_budget_kzt": _num(pm.group(1)) if pm else None, "pass_statuses": {}}
        for d in pane.select(".yoda-apex-line-chart"):
            o = _chart(d)
            if o.get("chart", {}).get("type") == "donut":
                y["pass_statuses"] = dict(zip(o.get("labels", []), o.get("series", [])))
        years[year] = y
    out["budget_by_year"] = years

    # Registry counters (drivers, owners, vehicles, trailers)
    reg = {}
    for lbl in ["водителей", "владельцев ТС", "ТС", "прицепов"]:
        m = re.search(r"Количество зарегистрированных " + re.escape(lbl) + r"\s+(\d+)\s+за последние 7 дней:\s+(\d+)", text)
        if m:
            reg[lbl] = {"total": int(m.group(1)), "last_7_days": int(m.group(2))}
    out["registry"] = reg

    # Border post load
    pm = re.search(r"Загруженность постов\s+Актуально на:\s*(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", text)
    out["posts_updated_at"] = pm.group(1) if pm else None
    posts = []
    for row in soup.select(".square-chart-row"):
        name_el = row.select_one(".square-chart-name")
        if not name_el:
            continue
        flag = name_el.select_one(".country-flag")
        country = None
        if flag:
            c = [x for x in flag["class"] if x.startswith("country-flag-")]
            country = c[0].replace("country-flag-", "").upper() if c else None
        days = []
        for sq in row.select(".square[title]"):
            t = _clean(BeautifulSoup(sq["title"].replace("<br", "\n<br"), "html.parser").get_text())
            lvl = next((int(x.split("-")[-1]) for x in sq["class"] if x.startswith("zag-level-")), None)
            dm = re.search(r"(\d{1,2} [а-я]{3})", t)
            day = {"date": dm.group(1) if dm else None, "level": lvl}
            fr = dict((int(k), int(v)) for k, v in re.findall(r"за (\d+) МРП: (\d+)", t))
            if fr:
                day["status"] = "open"; day["free"] = fr
            elif "не открыто" in t:
                day["status"] = "not_open"
            elif "Выходной" in t:
                day["status"] = "day_off"
            else:
                day["status"] = t
            days.append(day)
        if not days:
            continue
        open_days = [d for d in days if d["status"] == "open"]
        posts.append({
            "name": _clean(name_el.get_text()), "country": country, "days": days,
            "today": days[0],
            "free_total": {k: sum(d["free"].get(k, 0) for d in open_days) for k in (1, 100)},
            "open_days": len(open_days),
        })
    out["posts"] = posts
    return out


def fetch(force=False):
    if not force and _cache["data"] and time.time() - _cache["t"] < CACHE_TTL:
        return _cache["data"]
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 cgr-stat-bot"})
    r.raise_for_status()
    _cache["data"] = parse(r.text)
    _cache["t"] = time.time()
    return _cache["data"]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        d = parse(open(sys.argv[1], encoding="utf-8").read())
    else:
        d = fetch()
    full = "--full" in sys.argv
    if not full:
        for p in d["posts"]:
            p["days"] = p["days"][:3]
    print(json.dumps(d, ensure_ascii=False, indent=1))
