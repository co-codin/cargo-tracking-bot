import os
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services import cache, parser

HTML = os.environ.get("STAT_HTML", "/workspace/stat.html")


@pytest.fixture()
def client(monkeypatch):
    data = parser.parse(open(HTML, encoding="utf-8").read())
    monkeypatch.setattr(settings, "run_bot", False)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(cache, "_download", lambda: data)
    cache._cache.update(t=0.0, data=None)
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_stats(client):
    j = client.get("/api/stats").json()
    assert j["registered_users"]["total"] > 0 and "posts" not in j


def test_posts(client):
    j = client.get("/api/posts").json()
    assert len(j["posts"]) > 40


def test_post_fuzzy(client):
    j = client.get("/api/posts/ljcnsr").json()
    assert j["post"]["name"] == "Достык - Алашанькоу" and j["corrected"]


def test_post_not_found(client):
    assert client.get("/api/posts/xyz123").status_code == 404


def test_cache_stale(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", None)
    data = parser.parse(open(HTML, encoding="utf-8").read())
    monkeypatch.setattr(cache, "_download", lambda: data)
    cache._cache.update(t=0.0, data=None)
    assert cache.fetch()["stale"] is False
    def boom():
        raise ConnectionError("down")
    monkeypatch.setattr(cache, "_download", boom)
    assert cache.fetch(force=True)["stale"] is True
