import time
from io import StringIO
from threading import Lock

import pandas as pd
import requests
import yfinance as yf

_CACHE = {}
_LOCK = Lock()

MARKETS = [
    ("^KS11", "KOSPI", ""),
    ("^KQ11", "KOSDAQ", ""),
    ("^GSPC", "S&P 500", ""),
    ("^IXIC", "NASDAQ", ""),
    ("^VIX", "VIX", ""),
    ("KRW=X", "USD/KRW", "₩"),
    ("^TNX", "US 10Y", "%"),
]

FRED_SERIES = [
    ("DGS10", "미국 10년물", "%", "last"),
    ("FEDFUNDS", "Fed Funds", "%", "last"),
    ("CPIAUCSL", "미국 CPI YoY", "%", "yoy"),
    ("UNRATE", "미국 실업률", "%", "last"),
]


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


def _download(symbols, period="2mo"):
    return yf.download(
        symbols,
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=False,
        threads=True,
        group_by="column",
    )


def _series(frame, field, symbol):
    if frame.empty:
        return pd.Series(dtype=float)
    try:
        if isinstance(frame.columns, pd.MultiIndex):
            if (field, symbol) in frame.columns:
                return pd.to_numeric(
                    frame[(field, symbol)],
                    errors="coerce",
                )
            if (symbol, field) in frame.columns:
                return pd.to_numeric(
                    frame[(symbol, field)],
                    errors="coerce",
                )
        if field in frame.columns:
            return pd.to_numeric(
                frame[field],
                errors="coerce",
            )
    except Exception:
        pass
    return pd.Series(dtype=float)


def get_market_overview():
    def load():
        symbols = [x[0] for x in MARKETS]
        frame = _download(symbols, "2mo")
        result = []

        for symbol, name, suffix in MARKETS:
            closes = _series(frame, "Close", symbol).dropna()
            try:
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) > 1 else last
                change = last - prev
                pct = change / prev * 100 if prev else 0
                result.append({
                    "symbol": symbol,
                    "name": name,
                    "value": last,
                    "change": change,
                    "percent": pct,
                    "suffix": suffix,
                    "spark": closes.tail(30).tolist(),
                })
            except Exception:
                result.append({
                    "symbol": symbol,
                    "name": name,
                    "value": None,
                    "change": None,
                    "percent": None,
                    "suffix": suffix,
                    "spark": [],
                })
        return result

    # Batch request + cache is much faster than seven separate downloads.
    return _cached("markets-batch-v2", 120, load)


def _fred(series_id):
    response = requests.get(
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
        timeout=8,
    )
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    col = frame.columns[-1]
    frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=[col])[col].astype(float).tolist()


def get_macro_overview():
    def load():
        result = []
        for sid, name, suffix, mode in FRED_SERIES:
            try:
                values = _fred(sid)
                if mode == "yoy":
                    yoy = [
                        (values[i] / values[i - 12] - 1) * 100
                        for i in range(12, len(values))
                        if values[i - 12] != 0
                    ]
                    value = yoy[-1]
                    prev = yoy[-2] if len(yoy) > 1 else value
                    spark = yoy[-30:]
                else:
                    value = values[-1]
                    prev = values[-2] if len(values) > 1 else value
                    spark = values[-30:]

                result.append({
                    "id": sid,
                    "name": name,
                    "value": value,
                    "change": value - prev,
                    "suffix": suffix,
                    "spark": spark,
                })
            except Exception:
                result.append({
                    "id": sid,
                    "name": name,
                    "value": None,
                    "change": None,
                    "suffix": suffix,
                    "spark": [],
                })
        return result

    return _cached("macro-v2", 1800, load)


def _news_item(raw, label):
    content = raw.get("content") if isinstance(raw, dict) else None
    src = content if isinstance(content, dict) else raw
    if not isinstance(src, dict):
        return None

    title = src.get("title")
    if not title:
        return None

    provider = src.get("provider")
    publisher = (
        provider.get("displayName", "")
        if isinstance(provider, dict)
        else src.get("publisher", "")
    )

    url = ""
    for key in ("canonicalUrl", "clickThroughUrl"):
        value = src.get(key)
        if isinstance(value, dict) and value.get("url"):
            url = value["url"]
            break

    url = url or src.get("link") or src.get("url") or ""

    return {
        "title": str(title),
        "publisher": str(publisher),
        "url": str(url),
        "symbol": label,
    }


def get_watchlist_news(items, limit=8):
    symbols = []
    for item in items:
        symbol = item.get("symbol", "")
        if item.get("market") == "KR":
            symbol = (
                f"{symbol}.KQ"
                if "KOSDAQ" in str(item.get("exchange", "")).upper()
                else f"{symbol}.KS"
            )
        if symbol:
            symbols.append(
                (symbol, item.get("name") or item.get("symbol"))
            )

    def load():
        result = []
        seen = set()
        for symbol, label in symbols[:6]:
            try:
                for raw in (yf.Ticker(symbol).news or [])[:5]:
                    item = _news_item(raw, label)
                    if not item:
                        continue
                    key = item["title"].lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append(item)
                    if len(result) >= limit:
                        return result
            except Exception:
                pass
        return result

    return _cached(
        "news-v2:" + ",".join(s for s, _ in symbols[:6]),
        600,
        load,
    )


def get_sparkline_svg(market, exchange, symbol, width=300, height=74):
    """Return a lightweight 30-trading-day SVG sparkline for a stock card."""
    yahoo_symbol = symbol
    if market == "KR":
        yahoo_symbol = (
            f"{symbol}.KQ"
            if "KOSDAQ" in str(exchange).upper()
            else f"{symbol}.KS"
        )

    def load():
        try:
            frame = yf.download(
                yahoo_symbol,
                period="2mo",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if frame.empty:
                return ""
            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)
            closes = pd.to_numeric(frame["Close"], errors="coerce").dropna().tail(30).tolist()
            if len(closes) < 2:
                return ""

            lo, hi = min(closes), max(closes)
            span = max(hi - lo, 1e-9)
            pad_x, pad_y = 4, 6
            usable_w = width - pad_x * 2
            usable_h = height - pad_y * 2
            points = []
            for i, value in enumerate(closes):
                x = pad_x + usable_w * i / (len(closes) - 1)
                y = pad_y + usable_h * (hi - value) / span
                points.append(f"{x:.1f},{y:.1f}")

            stroke = "var(--red)" if closes[-1] >= closes[0] else "var(--down)"
            return (
                f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
                f'preserveAspectRatio="none" aria-label="30일 미니차트">'
                f'<polyline points="{" ".join(points)}" fill="none" '
                f'stroke="{stroke}" stroke-width="2.1" '
                f'stroke-linecap="round" stroke-linejoin="round" />'
                f'</svg>'
            )
        except Exception:
            return ""

    return _cached(f"spark-v08:{market}:{exchange}:{symbol}", 600, load)
