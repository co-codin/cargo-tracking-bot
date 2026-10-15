"""Парсер страницы https://cgr.qoldau.kz/ru/information/stat (server-rendered HTML)."""
import json, logging, os, re, sys, threading, time, uuid
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

try:
    import redis
except ImportError:  # redis is optional
    redis = None

URL = "https://cgr.qoldau.kz/ru/information/stat"
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


log = logging.getLogger("cgr.cache")
CACHE_TTL = int(os.environ.get("CACHE_TTL", "300"))
KEY, STALE_KEY, LOCK_KEY = "cgr:stat:data", "cgr:stat:stale", "cgr:stat:lock"
LOCK_TTL = 20  # seconds
_redis = {"client": None, "url": None}
_mem_lock = threading.Lock()


def _get_redis():
    url = os.environ.get("REDIS_URL")
    if not url or redis is None:
        return None
    try:
        if _redis["client"] is None or _redis["url"] != url:
            _redis["client"] = redis.Redis.from_url(url, socket_timeout=3, socket_connect_timeout=3,
                                                     decode_responses=True)
            _redis["url"] = url
        _redis["client"].ping()
        return _redis["client"]
    except Exception as e:
        log.warning("Redis unavailable (%s), using in-memory cache", e)
        return None


def _download():
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 cgr-stat-bot"})
    r.raise_for_status()
    return parse(r.text)


def _with_flag(data, stale):
    d = dict(data)
    d["stale"] = stale
    return d


def _fetch_memory(force):
    if not force and _cache["data"] and time.time() - _cache["t"] < CACHE_TTL:
        log.debug("memory cache hit")
        return _with_flag(_cache["data"], False)
    with _mem_lock:  # single-flight within the process
        if not force and _cache["data"] and time.time() - _cache["t"] < CACHE_TTL:
            log.debug("memory cache hit (after lock)")
            return _with_flag(_cache["data"], False)
        log.debug("memory cache miss, fetching site")
        try:
            data = _download()
        except Exception:
            if _cache["data"]:
                log.warning("site unavailable, serving stale in-memory data", exc_info=True)
                return _with_flag(_cache["data"], True)
            raise
        _cache["data"], _cache["t"] = data, time.time()
        return _with_flag(data, False)


def _fetch_redis(r, force):
    if not force:
        raw = r.get(KEY)
        if raw:
            log.debug("redis cache hit")
            return _with_flag(json.loads(raw), False)
    log.debug("redis cache miss")
    token = uuid.uuid4().hex
    got = r.set(LOCK_KEY, token, nx=True, ex=LOCK_TTL)
    if not got:
        # someone else is fetching: wait for the result
        deadline = time.time() + LOCK_TTL
        while time.time() < deadline:
            time.sleep(0.3)
            raw = r.get(KEY)
            if raw:
                log.debug("redis cache filled by another worker")
                return _with_flag(json.loads(raw), False)
            if not r.exists(LOCK_KEY):
                break
        log.debug("lock wait expired, fetching ourselves")
    try:
        try:
            data = _download()
        except Exception:
            raw = r.get(STALE_KEY)
            if raw:
                log.warning("site unavailable, serving stale data from redis", exc_info=True)
                return _with_flag(json.loads(raw), True)
            raise
        payload = json.dumps(data, ensure_ascii=False)
        pipe = r.pipeline()
        pipe.set(KEY, payload, ex=CACHE_TTL)
        pipe.set(STALE_KEY, payload)  # last good data, no TTL
        pipe.execute()
        _cache["data"], _cache["t"] = data, time.time()
        return _with_flag(data, False)
    finally:
        # release only our own lock
        r.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0",
               1, LOCK_KEY, token)


def _fix_keys(d):
    """JSON turns int dict keys into strings; restore them."""
    for p in d.get("posts", []):
        p["free_total"] = {int(k): v for k, v in p["free_total"].items()}
        for day in p["days"] + [p["today"]]:
            if "free" in day:
                day["free"] = {int(k): v for k, v in day["free"].items()}
    return d


def fetch(force=False):
    """Return parsed data; d["stale"] is True when the site was down and old data is served."""
    r = _get_redis()
    if r is not None:
        try:
            return _fix_keys(_fetch_redis(r, force))
        except (redis.RedisError, OSError) as e:
            log.warning("Redis error (%s), falling back to in-memory cache", e)
    return _fetch_memory(force)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        d = parse(open(sys.argv[1], encoding="utf-8").read())
    else:
        d = fetch()
    full = "--full" in sys.argv
    if not full:
        for p in d["posts"]:
            p["days"] = p["days"][:3]
    d.pop("stale", None)
    print(json.dumps(d, ensure_ascii=False, indent=1))
