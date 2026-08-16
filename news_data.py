import html
import os
import re
import time
from threading import Lock

import requests

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

_CACHE = {}
_LOCK = Lock()


def _cached(key, ttl, loader):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = loader()
    with _LOCK:
        _CACHE[key] = (now, value)
    return value


def naver_news_enabled():
    return bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET)


def _clean(text):
    value = html.unescape(str(text or ""))
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _key(title):
    value = _clean(title).lower()
    value = re.sub(r"[^0-9a-z가-힣]+", "", value)
    return value[:120]


def get_naver_news(query, display=8):
    query = (query or "").strip()
    if not query or not naver_news_enabled():
        return []

    def load():
        response = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers={
                "X-Naver-Client-Id": NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            params={
                "query": query,
                "display": min(max(int(display), 1), 100),
                "start": 1,
                "sort": "date",
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        result = []
        for item in payload.get("items", []) or []:
            result.append({
                "title": _clean(item.get("title")),
                "publisher": "NAVER 뉴스",
                "url": item.get("originallink") or item.get("link") or "",
                "published": item.get("pubDate") or "",
                "description": _clean(item.get("description")),
                "source_type": "NAVER",
                "symbol": query,
            })
        return result

    return _cached(f"naver:{query}:{display}", 600, load)


def merge_news(yahoo_items, naver_items, limit=16):
    merged = []
    seen = set()
    for item in list(naver_items or []) + list(yahoo_items or []):
        title = item.get("title") or ""
        key = _key(title)
        if not key or key in seen:
            continue
        seen.add(key)
        copy = dict(item)
        copy.setdefault("source_type", "YAHOO")
        merged.append(copy)
        if len(merged) >= limit:
            break
    return merged


def get_naver_news_for_watchlist(items, per_symbol=3, limit=12):
    if not naver_news_enabled():
        return []
    result = []
    seen = set()
    for item in (items or [])[:5]:
        query = item.get("name") or item.get("symbol") or ""
        for news in get_naver_news(query, per_symbol):
            key = _key(news.get("title"))
            if not key or key in seen:
                continue
            seen.add(key)
            news["symbol"] = query
            result.append(news)
            if len(result) >= limit:
                return result
    return result
