import html
import time
from threading import Lock

import pandas as pd
import yfinance as yf

_CACHE = {}
_LOCK = Lock()

# "시가총액 대표"는 매번 전체 거래소를 스크리닝하지 않고,
# 안정적으로 보여줄 대형주 대표 universe를 사용합니다.
# "거래 활발"은 같은 universe에서 최신 거래량 기준으로 동적 정렬합니다.
KR_UNIVERSE = [
    {"symbol": "005930", "name": "삼성전자", "exchange": "KOSPI", "yf": "005930.KS"},
    {"symbol": "000660", "name": "SK하이닉스", "exchange": "KOSPI", "yf": "000660.KS"},
    {"symbol": "373220", "name": "LG에너지솔루션", "exchange": "KOSPI", "yf": "373220.KS"},
    {"symbol": "207940", "name": "삼성바이오로직스", "exchange": "KOSPI", "yf": "207940.KS"},
    {"symbol": "005380", "name": "현대차", "exchange": "KOSPI", "yf": "005380.KS"},
    {"symbol": "000270", "name": "기아", "exchange": "KOSPI", "yf": "000270.KS"},
    {"symbol": "068270", "name": "셀트리온", "exchange": "KOSPI", "yf": "068270.KS"},
    {"symbol": "105560", "name": "KB금융", "exchange": "KOSPI", "yf": "105560.KS"},
    {"symbol": "055550", "name": "신한지주", "exchange": "KOSPI", "yf": "055550.KS"},
    {"symbol": "035420", "name": "NAVER", "exchange": "KOSPI", "yf": "035420.KS"},
    {"symbol": "035720", "name": "카카오", "exchange": "KOSPI", "yf": "035720.KS"},
    {"symbol": "012450", "name": "한화에어로스페이스", "exchange": "KOSPI", "yf": "012450.KS"},
    {"symbol": "009150", "name": "삼성전기", "exchange": "KOSPI", "yf": "009150.KS"},
    {"symbol": "006400", "name": "삼성SDI", "exchange": "KOSPI", "yf": "006400.KS"},
    {"symbol": "086790", "name": "하나금융지주", "exchange": "KOSPI", "yf": "086790.KS"},
    {"symbol": "247540", "name": "에코프로비엠", "exchange": "KOSDAQ", "yf": "247540.KQ"},
    {"symbol": "086520", "name": "에코프로", "exchange": "KOSDAQ", "yf": "086520.KQ"},
    {"symbol": "196170", "name": "알테오젠", "exchange": "KOSDAQ", "yf": "196170.KQ"},
]

US_UNIVERSE = [
    {"symbol": "NVDA", "name": "NVIDIA", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "name": "Microsoft", "exchange": "NASDAQ"},
    {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ"},
    {"symbol": "AMZN", "name": "Amazon", "exchange": "NASDAQ"},
    {"symbol": "GOOGL", "name": "Alphabet", "exchange": "NASDAQ"},
    {"symbol": "META", "name": "Meta Platforms", "exchange": "NASDAQ"},
    {"symbol": "AVGO", "name": "Broadcom", "exchange": "NASDAQ"},
    {"symbol": "TSLA", "name": "Tesla", "exchange": "NASDAQ"},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway", "exchange": "NYSE"},
    {"symbol": "JPM", "name": "JPMorgan Chase", "exchange": "NYSE"},
    {"symbol": "WMT", "name": "Walmart", "exchange": "NYSE"},
    {"symbol": "LLY", "name": "Eli Lilly", "exchange": "NYSE"},
    {"symbol": "V", "name": "Visa", "exchange": "NYSE"},
    {"symbol": "MA", "name": "Mastercard", "exchange": "NYSE"},
    {"symbol": "NFLX", "name": "Netflix", "exchange": "NASDAQ"},
    {"symbol": "AMD", "name": "AMD", "exchange": "NASDAQ"},
    {"symbol": "PLTR", "name": "Palantir", "exchange": "NASDAQ"},
    {"symbol": "INTC", "name": "Intel", "exchange": "NASDAQ"},
]

MARKET_CAP_ORDER_KR = [x["symbol"] for x in KR_UNIVERSE]
MARKET_CAP_ORDER_US = [x["symbol"] for x in US_UNIVERSE]


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


def _download(symbols, period="2mo", interval="1d"):
    return yf.download(
        symbols,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
    )


def _series_for(frame, field, symbol):
    try:
        if isinstance(frame.columns, pd.MultiIndex):
            if (field, symbol) in frame.columns:
                return pd.to_numeric(frame[(field, symbol)], errors="coerce")
            if (symbol, field) in frame.columns:
                return pd.to_numeric(frame[(symbol, field)], errors="coerce")
        if field in frame.columns:
            return pd.to_numeric(frame[field], errors="coerce")
    except Exception:
        pass
    return pd.Series(dtype=float)


def _quote_row(meta, closes, volumes, market):
    closes = closes.dropna()
    volumes = volumes.dropna()

    last = float(closes.iloc[-1]) if len(closes) else None
    prev = float(closes.iloc[-2]) if len(closes) > 1 else last
    change = (last - prev) if last is not None and prev is not None else None
    pct = (change / prev * 100) if change is not None and prev not in (None, 0) else None
    volume = float(volumes.iloc[-1]) if len(volumes) else 0.0

    result = {
        "symbol": meta["symbol"],
        "name": meta["name"],
        "exchange": meta["exchange"],
        "market": market,
        "price": last,
        "change": change,
        "percent": pct,
        "volume": volume,
        "spark": closes.tail(30).tolist(),
    }
    return result


def _load_universe(universe, market):
    yf_symbols = [x.get("yf", x["symbol"]) for x in universe]
    frame = _download(yf_symbols, "2mo", "1d")
    rows = []

    for meta in universe:
        ys = meta.get("yf", meta["symbol"])
        closes = _series_for(frame, "Close", ys)
        volumes = _series_for(frame, "Volume", ys)
        row = _quote_row(meta, closes, volumes, market)
        if row["price"] is not None:
            rows.append(row)
    return rows


def get_representative_stocks(market="KR", mode="cap", limit=6):
    market = market.upper()
    mode = mode.lower()
    key = f"representative:{market}:{mode}:{limit}"

    def load():
        universe = KR_UNIVERSE if market == "KR" else US_UNIVERSE
        rows = _load_universe(universe, market)

        if mode == "volume":
            rows.sort(key=lambda x: x.get("volume") or 0, reverse=True)
        else:
            order = MARKET_CAP_ORDER_KR if market == "KR" else MARKET_CAP_ORDER_US
            rank = {symbol: i for i, symbol in enumerate(order)}
            rows.sort(key=lambda x: rank.get(x["symbol"], 9999))

        return rows[:limit]

    return _cached(key, 180, load)


def sparkline_svg(values, width=260, height=58):
    if not values or len(values) < 2:
        return ""

    values = [float(x) for x in values if x is not None]
    if len(values) < 2:
        return ""

    lo, hi = min(values), max(values)
    span = max(hi - lo, 1e-9)
    pad_x, pad_y = 3, 5
    uw = width - pad_x * 2
    uh = height - pad_y * 2

    points = []
    for i, value in enumerate(values):
        x = pad_x + uw * i / (len(values) - 1)
        y = pad_y + uh * (hi - value) / span
        points.append(f"{x:.1f},{y:.1f}")

    positive = values[-1] >= values[0]
    stroke = "#ef4444" if positive else "#3b82f6"
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'preserveAspectRatio="none">'
        f'<polyline points="{html.escape(" ".join(points))}" '
        f'fill="none" stroke="{stroke}" stroke-width="2.1" '
        f'stroke-linecap="round" stroke-linejoin="round" />'
        f'</svg>'
    )
