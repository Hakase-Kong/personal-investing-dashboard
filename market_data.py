from functools import lru_cache

import yfinance as yf


KR_NAMES = [
    ("005930", "삼성전자", "KOSPI"),
    ("000660", "SK하이닉스", "KOSPI"),
    ("373220", "LG에너지솔루션", "KOSPI"),
    ("207940", "삼성바이오로직스", "KOSPI"),
    ("005380", "현대차", "KOSPI"),
    ("000270", "기아", "KOSPI"),
    ("068270", "셀트리온", "KOSPI"),
    ("035420", "NAVER", "KOSPI"),
    ("035720", "카카오", "KOSPI"),
    ("105560", "KB금융", "KOSPI"),
    ("055550", "신한지주", "KOSPI"),
    ("051910", "LG화학", "KOSPI"),
    ("006400", "삼성SDI", "KOSPI"),
    ("009150", "삼성전기", "KOSPI"),
    ("012450", "한화에어로스페이스", "KOSPI"),
    ("032830", "삼성생명", "KOSPI"),
    ("000810", "삼성화재", "KOSPI"),
    ("086790", "하나금융지주", "KOSPI"),
    ("316140", "우리금융지주", "KOSPI"),
    ("247540", "에코프로비엠", "KOSDAQ"),
]


def search_stocks(query: str):
    q = query.strip()
    q_lower = q.lower()
    results = []

    for symbol, name, exchange in KR_NAMES:
        if q_lower in symbol.lower() or q_lower in name.lower():
            results.append({
                "symbol": symbol,
                "name": name,
                "market": "KR",
                "exchange": exchange,
            })

    if q.isdigit() and len(q) == 6 and not any(
        x["symbol"] == q for x in results
    ):
        results.insert(0, {
            "symbol": q,
            "name": q,
            "market": "KR",
            "exchange": "KR",
        })

    try:
        search = yf.Search(q, max_results=10, news_count=0)
        for item in getattr(search, "quotes", []) or []:
            quote_type = str(item.get("quoteType", "")).upper()
            if quote_type not in {"EQUITY", "ETF"}:
                continue

            symbol = str(item.get("symbol", "")).strip()
            if not symbol or symbol.endswith(".KS") or symbol.endswith(".KQ"):
                continue

            results.append({
                "symbol": symbol,
                "name": str(
                    item.get("longname")
                    or item.get("shortname")
                    or item.get("name")
                    or symbol
                ),
                "market": "US",
                "exchange": str(
                    item.get("exchange")
                    or item.get("exchDisp")
                    or "US"
                ).upper(),
            })
    except Exception:
        pass

    def score(item):
        symbol = item["symbol"].lower()
        name = item["name"].lower()
        if symbol == q_lower:
            return 0
        if name == q_lower:
            return 1
        if symbol.startswith(q_lower):
            return 2
        if name.startswith(q_lower):
            return 3
        return 4

    unique = {}
    for item in results:
        unique[(item["market"], item["symbol"])] = item

    return sorted(unique.values(), key=score)[:12]


@lru_cache(maxsize=256)
def ticker(symbol):
    return yf.Ticker(symbol)


def get_us_quote(symbol: str):
    t = ticker(symbol)
    info = t.fast_info

    price = _float(getattr(info, "last_price", None))
    previous_close = _float(getattr(info, "previous_close", None))

    if price is None:
        history = t.history(period="5d", interval="1d")
        if history.empty:
            raise RuntimeError(f"{symbol} 가격 조회 실패")
        price = float(history["Close"].iloc[-1])
        if len(history) > 1:
            previous_close = float(history["Close"].iloc[-2])

    change = None
    percent = None
    if previous_close not in (None, 0):
        change = price - previous_close
        percent = change / previous_close * 100

    return {
        "price": price,
        "change": change,
        "change_percent": percent,
        "currency": "USD",
    }


def _float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
