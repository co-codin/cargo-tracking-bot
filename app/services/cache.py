"""Кэш разобранных данных: Redis (single-flight, устаревшие данные) или память процесса."""
import json, logging, threading, time, uuid

try:
    import redis
except ImportError:  # redis is optional
    redis = None

from app.config import settings
from app.services import parser

_cache = {"t": 0.0, "data": None}
log = logging.getLogger("cgr.cache")
KEY, STALE_KEY, LOCK_KEY = "cgr:stat:data", "cgr:stat:stale", "cgr:stat:lock"
LOCK_TTL = 20  # seconds
FORCE_MIN_AGE = 45  # «Обновить» идёт на сайт, только если кэшу больше 45 с
_redis = {"client": None, "url": None}
_mem_lock = threading.Lock()


def _get_redis():
    url = settings.redis_url
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
    return parser.download(settings.source_url)


def _with_flag(data, stale):
    d = dict(data)
    d["stale"] = stale
    return d


def _fetch_memory(force):
    if force and _cache["data"] and time.time() - _cache["t"] < FORCE_MIN_AGE:
        return _with_flag(_cache["data"], False)
    if not force and _cache["data"] and time.time() - _cache["t"] < settings.cache_ttl:
        log.debug("memory cache hit")
        return _with_flag(_cache["data"], False)
    with _mem_lock:  # single-flight within the process
        if not force and _cache["data"] and time.time() - _cache["t"] < settings.cache_ttl:
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
    raw = r.get(KEY)
    if force and raw:
        ttl = r.ttl(KEY)
        if ttl is not None and ttl > 0 and settings.cache_ttl - ttl < FORCE_MIN_AGE:
            log.debug("forced refresh ignored: cache is fresh")
            return _with_flag(json.loads(raw), False)
    if not force:
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
        pipe.set(KEY, payload, ex=settings.cache_ttl)
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


