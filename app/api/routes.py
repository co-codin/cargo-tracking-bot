"""HTTP API: /health и JSON со статистикой."""
import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.services import cache, matching

router = APIRouter()


async def _data():
    try:
        return await asyncio.to_thread(cache.fetch)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Источник недоступен: {e}")


@router.get("/health")
async def health(request: Request):
    bot = getattr(request.app.state, "bot_mode", None)
    r = cache._get_redis()
    return {"status": "ok", "bot": bot, "redis": "ok" if r is not None else "unavailable (memory cache)"}


@router.get("/api/stats")
async def api_stats():
    d = await _data()
    return {k: v for k, v in d.items() if k != "posts"}


def _post_summary(p):
    t = p["today"]
    return {"name": p["name"], "country": p["country"], "today": t,
            "free_total": p["free_total"], "open_days": p["open_days"]}


@router.get("/api/posts")
async def api_posts():
    d = await _data()
    return {"updated_at": d["posts_updated_at"], "stale": d.get("stale", False),
            "posts": [_post_summary(p) for p in d["posts"]]}


@router.get("/api/posts/{name}")
async def api_post(name: str):
    d = await _data()
    kind, res, corrected = matching.resolve(d["posts"], name)
    if kind == "one":
        return {"updated_at": d["posts_updated_at"], "stale": d.get("stale", False),
                "corrected": corrected, "post": res}
    if kind == "many":
        raise HTTPException(status_code=404,
                            detail={"message": "Неоднозначный запрос", "suggestions": [p["name"] for p in res]})
    raise HTTPException(status_code=404, detail={"message": "Пункт пропуска не найден", "suggestions": []})
