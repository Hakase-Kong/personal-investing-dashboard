import os
import time
from datetime import datetime, timedelta
from io import StringIO
from threading import Lock
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

_CACHE = {}
_LOCK = Lock()

FUTURES = [
    ("ES=F", "S&P 500 E-mini"),
    ("NQ=F", "NASDAQ 100 E-mini"),
    ("YM=F", "Dow Futures"),
    ("RTY=F", "Russell 2000 Futures"),
    ("CL=F", "WTI Crude Oil"),
    ("GC=F", "Gold"),
    ("SI=F", "Silver"),
    ("HG=F", "Copper"),
]

FX = [
    ("KRW=X", "USD/KRW"),
    ("JPYKRW=X", "JPY/KRW"),
    ("EURKRW=X", "EUR/KRW"),
    ("CNYKRW=X", "CNY/KRW"),
    ("JPY=X", "USD/JPY"),
    ("EURUSD=X", "EUR/USD"),
    ("GBPUSD=X", "GBP/USD"),
]

US_TREASURY = [
    ("DGS1MO", "1M"),
    ("DGS3MO", "3M"),
    ("DGS6MO", "6M"),
    ("DGS1", "1Y"),
    ("DGS2", "2Y"),
    ("DGS5", "5Y"),
    ("DGS10", "10Y"),
    ("DGS30", "30Y"),
]

KR_TENORS = ["1년", "2년", "3년", "5년", "10년", "20년", "30년"]


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


def _batch_snapshot(items):
    symbols = [s for s, _ in items]
    frame = yf.download(
        symbols,
        period="2mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
    )

    result = []
    for symbol, name in items:
        try:
            if isinstance(frame.columns, pd.MultiIndex):
                closes = pd.to_numeric(frame[("Close", symbol)], errors="coerce").dropna()
            else:
                closes = pd.to_numeric(frame["Close"], errors="coerce").dropna()
            if closes.empty:
                raise RuntimeError("no data")
            last = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else last
            change = last - prev
            pct = change / prev * 100 if prev else 0.0
            result.append({
                "symbol": symbol,
                "name": name,
                "value": last,
                "change": change,
                "percent": pct,
                "spark": closes.tail(30).tolist(),
            })
        except Exception:
            result.append({
                "symbol": symbol,
                "name": name,
                "value": None,
                "change": None,
                "percent": None,
                "spark": [],
            })
    return result


def get_futures_snapshot():
    return _cached("futures", 60, lambda: _batch_snapshot(FUTURES))


def get_fx_snapshot():
    return _cached("fx", 60, lambda: _batch_snapshot(FX))


def _fred_latest(series_id):
    response = requests.get(
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
        timeout=8,
    )
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    col = frame.columns[-1]
    values = pd.to_numeric(frame[col], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.iloc[-1])


def get_us_yield_curve():
    def load():
        rows = []
        for series_id, tenor in US_TREASURY:
            try:
                value = _fred_latest(series_id)
            except Exception:
                value = None
            rows.append({"tenor": tenor, "value": value, "series": series_id})
        return rows
    return _cached("us-curve", 1800, load)


def _ecos_key():
    return os.getenv("ECOS_API_KEY", "").strip() or "sample"


def _ecos_items():
    key = _ecos_key()
    url = f"https://ecos.bok.or.kr/api/StatisticItemList/{key}/json/kr/1/300/817Y002/"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    body = response.json()
    rows = (body.get("StatisticItemList") or {}).get("row") or []
    items = []
    for row in rows:
        code = row.get("ITEM_CODE") or row.get("ITEM_CODE1")
        name = row.get("ITEM_NAME") or row.get("ITEM_NAME1") or ""
        if code and name:
            items.append((str(code), str(name)))
    return items


def _ecos_latest(stat_code, item_code, lookback_days=30):
    key = _ecos_key()
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    start = today - timedelta(days=lookback_days)
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/"
        f"{stat_code}/D/{start:%Y%m%d}/{today:%Y%m%d}/{item_code}/"
    )
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    body = response.json()
    rows = (body.get("StatisticSearch") or {}).get("row") or []
    values = []
    for row in rows:
        try:
            values.append((row.get("TIME"), float(row.get("DATA_VALUE"))))
        except Exception:
            pass
    values.sort(key=lambda x: x[0] or "")
    return values[-1][1] if values else None


def get_kr_yield_curve():
    def load():
        try:
            items = _ecos_items()
        except Exception:
            return [{"tenor": t.replace("년", "Y"), "value": None, "name": f"국고채({t})"} for t in KR_TENORS]

        result = []
        for tenor in KR_TENORS:
            target = None
            for code, name in items:
                compact = name.replace(" ", "")
                if "국고채" in compact and tenor in compact:
                    target = (code, name)
                    break
            if not target:
                result.append({"tenor": tenor.replace("년", "Y"), "value": None, "name": f"국고채({tenor})"})
                continue
            try:
                value = _ecos_latest("817Y002", target[0])
            except Exception:
                value = None
            result.append({"tenor": tenor.replace("년", "Y"), "value": value, "name": target[1]})
        return result

    return _cached("kr-curve", 1800, load)


def get_us_extended_session(symbol):
    """Best-effort extended-hours snapshot for US stocks using Yahoo intraday data."""
    def load():
        frame = yf.download(
            symbol,
            period="1d",
            interval="1m",
            prepost=True,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if frame.empty:
            return {"premarket": None, "regular": None, "afterhours": None, "session": "CLOSED"}
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame = frame.reset_index()
        dt_col = "Datetime" if "Datetime" in frame.columns else frame.columns[0]
        frame[dt_col] = pd.to_datetime(frame[dt_col], utc=True, errors="coerce").dt.tz_convert("America/New_York")
        frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
        frame = frame.dropna(subset=[dt_col, "Close"])
        if frame.empty:
            return {"premarket": None, "regular": None, "afterhours": None, "session": "CLOSED"}

        def latest_between(start_hm, end_hm):
            times = frame[dt_col].dt.time
            sh, sm = start_hm
            eh, em = end_hm
            from datetime import time as dtime
            mask = (times >= dtime(sh, sm)) & (times < dtime(eh, em))
            subset = frame[mask]
            return float(subset["Close"].iloc[-1]) if not subset.empty else None

        pre = latest_between((4, 0), (9, 30))
        regular = latest_between((9, 30), (16, 0))
        post = latest_between((16, 0), (20, 0))
        now = datetime.now(ZoneInfo("America/New_York"))
        if now.weekday() >= 5:
            session = "CLOSED"
        elif (now.hour, now.minute) < (9, 30) and (now.hour, now.minute) >= (4, 0):
            session = "PRE"
        elif (now.hour, now.minute) < (16, 0) and (now.hour, now.minute) >= (9, 30):
            session = "REGULAR"
        elif (now.hour, now.minute) < (20, 0) and (now.hour, now.minute) >= (16, 0):
            session = "POST"
        else:
            session = "CLOSED"
        return {"premarket": pre, "regular": regular, "afterhours": post, "session": session}

    return _cached(f"extended:{symbol}", 30, load)
