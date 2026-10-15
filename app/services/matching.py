"""Fuzzy lookup of border crossings by name (Cyrillic, Latin transliteration, wrong keyboard layout)."""
import re

try:
    from rapidfuzz import fuzz

    def _ratio(a, b):
        return fuzz.ratio(a, b)
except ImportError:  # pragma: no cover
    import difflib

    def _ratio(a, b):
        return difflib.SequenceMatcher(None, a, b).ratio() * 100

CONFIDENT = 78   # minimal score to open a card directly
GAP = 8          # how far ahead the best match must be
MIN_SCORE = 60   # below this nothing is suggested

_LAT = [("shch", "щ"), ("sch", "щ"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"),
        ("ya", "я"), ("yu", "ю"), ("yo", "е"), ("ye", "е"),
        ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"), ("h", "х"),
        ("i", "и"), ("j", "ж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"),
        ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("w", "в"), ("x", "кс"),
        ("y", "ы"), ("z", "з")]
_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
_RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
_LAYOUT = str.maketrans(_EN, _RU)


def norm(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w]+|_", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def translit(s):
    out, i = [], 0
    while i < len(s):
        for lat, cyr in _LAT:
            if s.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                break
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def variants(query):
    """[(normalized text, was_converted)] for the raw query."""
    raw = (query or "").lower().strip()
    v = [(norm(raw), False)]
    if re.search(r"[a-z\[\];',.`]", raw):
        v.append((norm(raw.translate(_LAYOUT)), True))
        v.append((norm(translit(re.sub(r"[^a-z0-9 \-]", " ", raw))), True))
    seen, res = set(), []
    for t, c in v:
        if t and t not in seen:
            seen.add(t)
            res.append((t, c))
    return res


def name_parts(name):
    full = norm(name)
    parts = [norm(x) for x in re.split(r"\s+[-–—]\s+|\(|\)", name) if norm(x)]
    words = [w for w in full.split() if len(w) >= 3]
    return full, parts, words


def score(q, name):
    full, parts, words = name_parts(name)
    if q == full or q in parts:
        return 100
    best = 0
    for p in parts + words + [full]:
        if p.startswith(q):
            best = max(best, 97 if len(q) >= 3 else 70)
        elif q in p:
            best = max(best, 90 if len(q) >= 3 else 60)
    for p in parts + words:
        best = max(best, _ratio(q, p))
    best = max(best, _ratio(q, full))
    return best


def search(posts, query, limit=5):
    """Return list of (post, score, converted) sorted by score."""
    out = []
    vs = variants(query)
    for p in posts:
        s, conv = 0, False
        for q, c in vs:
            sc = score(q, p["name"])
            if c:
                sc -= 2  # prefer an exact interpretation of what the user typed
            if sc > s:
                s, conv = sc, c
        if s >= MIN_SCORE:
            out.append((p, s, conv))
    out.sort(key=lambda x: -x[1])
    return out[:limit]


def resolve(posts, query):
    """('one', post, corrected) | ('many', [posts], None) | ('none', None, None)."""
    res = search(posts, query)
    if not res:
        return "none", None, None
    top = res[0]
    second = res[1][1] if len(res) > 1 else 0
    if top[1] >= CONFIDENT and top[1] - second >= GAP:
        corrected = top[2] or top[1] < 90
        return "one", top[0], corrected
    return "many", [r[0] for r in res], None
