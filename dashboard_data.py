import html
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


def _hist(symbol, period="5d", interval="1d"):
    frame = yf.download(
        symbol,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if frame.empty:
        return pd.DataFrame()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    return frame


def get_market_overview():
    def load():
        result = []
        for symbol, name, suffix in MARKETS:
            try:
                df = _hist(symbol, "5d", "1d")
                closes = pd.to_numeric(df["Close"], errors="coerce").dropna()
                if closes.empty:
                    raise RuntimeError("no data")
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) > 1 else last
                chg = last - prev
                pct = (chg / prev * 100) if prev else 0.0
                result.append({
                    "symbol": symbol,
                    "name": name,
                    "value": last,
                    "change": chg,
                    "percent": pct,
                    "suffix": suffix,
                })
            except Exception:
                result.append({
                    "symbol": symbol,
                    "name": name,
                    "value": None,
                    "change": None,
                    "percent": None,
                    "suffix": suffix,
                })
        return result

    return _cached("market-overview", 60, load)


def _fred_values(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    value_col = frame.columns[-1]
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame = frame.dropna(subset=[value_col])
    return frame[value_col].astype(float).tolist()


def get_macro_overview():
    def load():
        result = []
        for series_id, name, suffix, mode in FRED_SERIES:
            try:
                values = _fred_values(series_id)
                if not values:
                    raise RuntimeError("no FRED data")

                if mode == "yoy":
                    if len(values) < 13:
                        raise RuntimeError("not enough CPI data")
                    value = (values[-1] / values[-13] - 1) * 100
                    previous = (values[-2] / values[-14] - 1) * 100 if len(values) >= 14 else value
                else:
                    value = values[-1]
                    previous = values[-2] if len(values) > 1 else value

                result.append({
                    "id": series_id,
                    "name": name,
                    "value": value,
                    "change": value - previous,
                    "suffix": suffix,
                })
            except Exception:
                result.append({
                    "id": series_id,
                    "name": name,
                    "value": None,
                    "change": None,
                    "suffix": suffix,
                })
        return result

    return _cached("macro-overview", 900, load)


def _extract_news_item(raw, fallback_symbol=""):
    content = raw.get("content") if isinstance(raw, dict) else None
    source = content if isinstance(content, dict) else raw
    if not isinstance(source, dict):
        return None

    title = source.get("title") or ""
    if not title:
        return None

    provider = source.get("provider")
    if isinstance(provider, dict):
        publisher = provider.get("displayName") or provider.get("name") or ""
    else:
        publisher = source.get("publisher") or ""

    url = ""
    canonical = source.get("canonicalUrl")
    click = source.get("clickThroughUrl")
    if isinstance(canonical, dict):
        url = canonical.get("url") or ""
    if not url and isinstance(click, dict):
        url = click.get("url") or ""
    if not url:
        url = source.get("link") or source.get("url") or ""

    published = source.get("pubDate") or source.get("providerPublishTime") or ""

    return {
        "title": str(title),
        "publisher": str(publisher),
        "url": str(url),
        "published": str(published),
        "symbol": fallback_symbol,
    }


def get_watchlist_news(items, limit=10):
    symbols = []
    for item in items:
        symbol = item.get("symbol", "")
        if item.get("market") == "KR":
            exchange = str(item.get("exchange", "")).upper()
            symbol = f"{symbol}.KQ" if "KOSDAQ" in exchange else f"{symbol}.KS"
        if symbol:
            symbols.append((symbol, item.get("name") or item.get("symbol")))

    def load():
        collected = []
        seen = set()
        for yahoo_symbol, label in symbols[:8]:
            try:
                news = yf.Ticker(yahoo_symbol).news or []
                for raw in news[:6]:
                    item = _extract_news_item(raw, label)
                    if not item:
                        continue
                    key = item["title"].strip().lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(item)
                    if len(collected) >= limit:
                        return collected
            except Exception:
                continue
        return collected

    key = "news:" + ",".join(x[0] for x in symbols[:8])
    return _cached(key, 300, load)


def get_sparkline_svg(market, exchange, symbol, width=300, height=74):
    yahoo_symbol = symbol
    if market == "KR":
        yahoo_symbol = (
            f"{symbol}.KQ"
            if "KOSDAQ" in str(exchange).upper()
            else f"{symbol}.KS"
        )

    def load():
        try:
            df = _hist(yahoo_symbol, "2mo", "1d")
            closes = pd.to_numeric(df["Close"], errors="coerce").dropna().tail(30)
            if len(closes) < 2:
                return ""

            values = closes.tolist()
            lo, hi = min(values), max(values)
            span = max(hi - lo, 1e-9)

            pad_x, pad_y = 4, 6
            usable_w = width - pad_x * 2
            usable_h = height - pad_y * 2

            points = []
            for i, value in enumerate(values):
                x = pad_x + usable_w * i / (len(values) - 1)
                y = pad_y + usable_h * (hi - value) / span
                points.append(f"{x:.1f},{y:.1f}")

            positive = values[-1] >= values[0]
            stroke = "#ef4444" if positive else "#3b82f6"
            fill = "rgba(239,68,68,.08)" if positive else "rgba(59,130,246,.08)"

            area_points = f"{pad_x},{height-pad_y} " + " ".join(points) + f" {width-pad_x},{height-pad_y}"

            return (
                f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
                f'preserveAspectRatio="none" aria-label="30일 일봉 미니차트">'
                f'<polygon points="{html.escape(area_points)}" fill="{fill}" />'
                f'<polyline points="{html.escape(" ".join(points))}" '
                f'fill="none" stroke="{stroke}" stroke-width="2.2" '
                f'stroke-linecap="round" stroke-linejoin="round" />'
                f'</svg>'
            )
        except Exception:
            return ""

    return _cached(
        f"spark:{market}:{exchange}:{symbol}",
        600,
        load,
    )
