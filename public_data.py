import time
from threading import Lock

import pandas as pd
import yfinance as yf
from kr_master import search_master

_CACHE = {}
_LOCK = Lock()

KR = [
    ("005930", "삼성전자", "KOSPI", "005930.KS"),
    ("000660", "SK하이닉스", "KOSPI", "000660.KS"),
    ("373220", "LG에너지솔루션", "KOSPI", "373220.KS"),
    ("207940", "삼성바이오로직스", "KOSPI", "207940.KS"),
    ("005380", "현대차", "KOSPI", "005380.KS"),
    ("000270", "기아", "KOSPI", "000270.KS"),
    ("068270", "셀트리온", "KOSPI", "068270.KS"),
    ("105560", "KB금융", "KOSPI", "105560.KS"),
    ("055550", "신한지주", "KOSPI", "055550.KS"),
    ("035420", "NAVER", "KOSPI", "035420.KS"),
    ("035720", "카카오", "KOSPI", "035720.KS"),
    ("012450", "한화에어로스페이스", "KOSPI", "012450.KS"),
    ("247540", "에코프로비엠", "KOSDAQ", "247540.KQ"),
]

US = [
    ("NVDA", "NVIDIA", "NASDAQ", "NVDA"),
    ("MSFT", "Microsoft", "NASDAQ", "MSFT"),
    ("AAPL", "Apple", "NASDAQ", "AAPL"),
    ("AMZN", "Amazon", "NASDAQ", "AMZN"),
    ("GOOGL", "Alphabet", "NASDAQ", "GOOGL"),
    ("META", "Meta Platforms", "NASDAQ", "META"),
    ("AVGO", "Broadcom", "NASDAQ", "AVGO"),
    ("TSLA", "Tesla", "NASDAQ", "TSLA"),
    ("BRK-B", "Berkshire Hathaway", "NYSE", "BRK-B"),
    ("JPM", "JPMorgan Chase", "NYSE", "JPM"),
    ("WMT", "Walmart", "NYSE", "WMT"),
    ("AMD", "AMD", "NASDAQ", "AMD"),
    ("NFLX", "Netflix", "NASDAQ", "NFLX"),
    ("PLTR", "Palantir", "NASDAQ", "PLTR"),
    ("ORCL", "Oracle", "NYSE", "ORCL"),
    ("COST", "Costco", "NASDAQ", "COST"),
    ("KO", "Coca-Cola", "NYSE", "KO"),
    ("CRM", "Salesforce", "NYSE", "CRM"),
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


def _series(frame, field, symbol):
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
            return pd.to_numeric(frame[field], errors="coerce")
    except Exception:
        pass
    return pd.Series(dtype=float)


def _load(rows, market):
    yf_symbols = [row[3] for row in rows]
    frame = yf.download(
        yf_symbols,
        period="2mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
    )

    result = []
    for symbol, name, exchange, yf_symbol in rows:
        closes = _series(frame, "Close", yf_symbol).dropna()
        volumes = _series(frame, "Volume", yf_symbol).dropna()
        if closes.empty:
            continue

        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) > 1 else last
        change = last - prev
        pct = change / prev * 100 if prev else 0

        result.append({
            "symbol": symbol,
            "name": name,
            "exchange": exchange,
            "market": market,
            "price": last,
            "change": change,
            "percent": pct,
            "volume": (
                float(volumes.iloc[-1])
                if len(volumes)
                else 0.0
            ),
            "spark": closes.tail(30).tolist(),
        })
    return result


def _attach_sparklines(rows, limit=20):
    if not rows:return rows
    symbols=[]; mapping={}
    for row in rows[:limit]:
        symbol=row.get('symbol','')
        if not symbol:continue
        matches=search_master(symbol,limit=5)
        exact=next((x for x in matches if x['symbol']==symbol),None)
        if exact:
            row['exchange']=exact['exchange']
            row['name']=row.get('name') or exact['name']
        ys=f"{symbol}.KQ" if row.get('exchange')=='KOSDAQ' else f"{symbol}.KS"
        symbols.append(ys); mapping[ys]=row
    if not symbols:return rows
    try:
        frame=yf.download(symbols,period='2mo',interval='1d',auto_adjust=False,progress=False,threads=True,group_by='column')
        for ys,row in mapping.items():
            closes=_series(frame,'Close',ys).dropna()
            if len(closes):row['spark']=closes.tail(30).tolist()
    except Exception:pass
    return rows

def get_representative_stocks(market='KR', mode='cap', limit=12, kis=None):
    market=market.upper(); mode=mode.lower()
    if market=='KR' and kis is not None and kis.enabled():
        def load_kis():
            try:
                rows=kis.get_volume_rank('0000',limit) if mode=='volume' else kis.get_market_cap_rank('0000',limit)
                rows=[r for r in rows if r.get('symbol')]
                return _attach_sparklines(rows,limit)
            except Exception:
                data=_load(KR,'KR')
                if mode=='volume':data.sort(key=lambda x:x.get('volume') or 0,reverse=True)
                return data[:limit]
        return _cached(f'kis-ranking:{mode}:{limit}',120,load_kis)
    def load():
        data=_load(US if market=='US' else KR,market)
        if mode=='volume':data.sort(key=lambda x:x.get('volume') or 0,reverse=True)
        return data[:limit]
    return _cached(f'representatives-v3:{market}:{mode}:{limit}',180,load)
