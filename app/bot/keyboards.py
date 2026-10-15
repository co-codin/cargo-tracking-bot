"""Инлайн-клавиатуры."""
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup

from app.bot.formatters import COUNTRY_ORDER, country, today_icon


def card_kb(i):
    return InlineKeyboardMarkup([[Btn("🔄 Обновить", callback_data=f"r:{i}"),
                                  Btn("📋 Все пункты", callback_data="all")]])


def countries_kb(d):
    codes = []
    for p in d["posts"]:
        if p["country"] not in codes:
            codes.append(p["country"])
    codes.sort(key=lambda c: COUNTRY_ORDER.index(c) if c in COUNTRY_ORDER else 99)
    rows = []
    for c in codes:
        fl, nm = country(c)
        n = sum(1 for p in d["posts"] if p["country"] == c)
        rows.append([Btn(f"{fl} {nm} ({n})", callback_data=f"c:{c}")])
    rows.append([Btn("📋 Все пункты списком", callback_data="all")])
    return InlineKeyboardMarkup(rows)


def country_posts_kb(d, code):
    rows = [[Btn(f"{today_icon(p)} {p['name']}", callback_data=f"p:{i}")]
            for i, p in enumerate(d["posts"]) if p["country"] == code]
    rows.append([Btn("⬅️ Назад к странам", callback_data="countries")])
    return InlineKeyboardMarkup(rows)


