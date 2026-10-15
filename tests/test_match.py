import json, os, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services import parser as P
from app.services.matching import resolve, variants

HTML = os.environ.get("STAT_HTML", "/workspace/stat.html")


@pytest.fixture(scope="module")
def posts():
    return P.parse(open(HTML, encoding="utf-8").read())["posts"]


@pytest.mark.parametrize("query,expected,corrected", [
    ("Достык", "Достык - Алашанькоу", False),
    ("дост", "Достык - Алашанькоу", False),
    ("достик", "Достык - Алашанькоу", True),
    ("dostyk", "Достык - Алашанькоу", True),
    ("ljcnsr", "Достык - Алашанькоу", True),
    ("хоргос", "Нур Жолы - Хоргос", False),
    ("харгос", "Нур Жолы - Хоргос", True),
    ("курык", "Порт Курык", False),
    ("нур-жолы", "Нур Жолы - Хоргос", False),
    ("Алашанькоу", "Достык - Алашанькоу", False),
])
def test_one(posts, query, expected, corrected):
    kind, post, corr = resolve(posts, query)
    assert kind == "one", (query, kind, post)
    assert post["name"] == expected
    assert corr == corrected


def test_not_found(posts):
    assert resolve(posts, "xyz123")[0] == "none"


def test_ambiguous(posts):
    kind, lst, _ = resolve(posts, "павловка")
    assert kind == "many"
    assert all("Павловка" in p["name"] for p in lst[:2])


def test_variants():
    assert ("достык", True) in variants("ljcnsr")
    assert ("достык", True) in variants("dostyk")
