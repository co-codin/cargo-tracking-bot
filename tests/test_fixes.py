import asyncio, os, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from telegram import Update
from telegram.ext import ApplicationHandlerStop

from app.config import settings
from app.bot import formatters as F
from app.bot import application as A
from app.bot.handlers import callbacks, commands, text, inline
from app.services import cache, parser, ratelimit

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "stat.html")


@pytest.fixture()
def data(monkeypatch):
    d = parser.parse(open(HTML, encoding="utf-8").read())
    monkeypatch.setattr(settings, "redis_url", None)
    calls = []
    monkeypatch.setattr(cache, "_download", lambda: calls.append(1) or d)
    cache._cache.update(t=0.0, data=None)
    return d, calls


def run(c):
    return asyncio.run(c)


# --- (A) refresh / rate limit
def test_force_uses_cache_when_fresh(data):
    _, calls = data
    cache.fetch(); cache.fetch(force=True)
    assert len(calls) == 1
    cache._cache["t"] = time.time() - 46
    cache.fetch(force=True)
    assert len(calls) == 2


class FakeRedis:
    def __init__(self, raw, ttl):
        self.raw, self._ttl = raw, ttl
    def get(self, k):
        return self.raw if k == cache.KEY else None
    def ttl(self, k):
        return self._ttl


def test_force_redis_fresh(monkeypatch):
    monkeypatch.setattr(cache, "_download", lambda: pytest.fail("should not download"))
    r = FakeRedis('{"posts": []}', settings.cache_ttl - 10)
    assert cache._fetch_redis(r, True)["posts"] == []


def test_token_bucket():
    b = ratelimit.TokenBucket(rate=1, burst=5)
    assert all(b.allow(1, now=0) for _ in range(5))
    assert not b.allow(1, now=0)
    assert b.allow(2, now=0)
    assert b.allow(1, now=1.0)


def test_rate_limit_callback_answer(monkeypatch):
    monkeypatch.setattr(A, "bot_limiter", ratelimit.TokenBucket(rate=0.0001, burst=1))
    cq = SimpleNamespace(answer=AsyncMock())
    upd = MagicMock(spec=Update); upd.effective_user = SimpleNamespace(id=7)
    upd.callback_query = cq; upd.inline_query = None
    run(A._rate_limit(upd, None))  # first passes
    with pytest.raises(ApplicationHandlerStop):
        run(A._rate_limit(upd, None))
    assert "подождите" in cq.answer.call_args[0][0]


def test_api_rate_limit(monkeypatch, data):
    from fastapi.testclient import TestClient
    from app.api import routes
    monkeypatch.setattr(settings, "run_bot", False)
    monkeypatch.setattr(routes, "api_limiter", ratelimit.TokenBucket(rate=0.0001, burst=2))
    from app.main import app
    with TestClient(app) as c:
        codes = [c.get("/api/stats").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# --- (B) robustness
def test_short():
    assert F.short(100000) == "100 тыс."
    assert F.short(1000) == "1 тыс."
    assert F.short(1500000) == "1,5 млн"
    assert F.short(29186988744) == "29,2 млрд"


def test_delta():
    assert F.delta(-5) == "▼ −5" and F.delta(5) == "▲ +5" and "+-" not in F.delta(-1000)


def test_split_chunks():
    blocks = ["\n".join(f"строка {i} " + "x" * 50 for i in range(200)) for _ in range(3)]
    ch = F.split_chunks(blocks)
    assert len(ch) > 1 and all(len(c) <= 4096 for c in ch)
    assert "\n".join(ch).split("\n") == "\n".join(blocks).split("\n")


def test_handlers_ignore_no_message(data):
    upd = SimpleNamespace(effective_message=None, message=None, callback_query=None, inline_query=None)
    ctx = SimpleNamespace(args=[], bot=SimpleNamespace(username="b"))
    for fn in (commands.start, commands.stats, commands.posts, commands.post, text.text_message, inline.inline_query):
        run(fn(upd, ctx))


def test_posts_escapes_and_limits(data):
    d, _ = data
    d["posts"][0]["name"] = "<b>Evil & Co</b>" + "я" * 3000
    for p in d["posts"][1:5]:
        p["name"] = "Длинное " * 300
    msg = SimpleNamespace(reply_text=AsyncMock())
    run(commands.posts(SimpleNamespace(effective_message=msg), None))
    texts = [c.args[0] for c in msg.reply_text.call_args_list]
    assert len(texts) > 1 and all(len(t) <= 4096 for t in texts)
    joined = "".join(texts)
    assert "&lt;b&gt;Evil &amp; Co" in joined and "<b>Evil" not in joined


def test_render_post_escapes(data):
    d, _ = data
    p = d["posts"][0]; p["name"] = "<x>"
    assert "<x>" not in F.card_text(d, p, corrected=True)


@pytest.mark.parametrize("bad", ["", "zzz", "p:abc", "r:", "p:99999"])
def test_bad_callback_answers(data, bad):
    cq = SimpleNamespace(data=bad, answer=AsyncMock(), message=None, edit_message_text=AsyncMock())
    run(callbacks.on_callback(SimpleNamespace(callback_query=cq, effective_message=None), None))
    assert cq.answer.await_count == 1


def test_error_handler_replies():
    msg = SimpleNamespace(reply_text=AsyncMock())
    upd = MagicMock(spec=Update); upd.callback_query = None; upd.effective_message = msg
    run(A._on_error(upd, SimpleNamespace(error=RuntimeError("x"))))
    assert "Что-то пошло не так" in msg.reply_text.call_args[0][0]
