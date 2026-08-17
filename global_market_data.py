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


US_BOND_SERIES = {tenor: series for series, tenor in US_TREASURY}


def _fred_history(series_id, years=5):
    response = requests.get(
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
        timeout=10,
    )
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    date_col, value_col = frame.columns[0], frame.columns[-1]
    result = pd.DataFrame({
        'date': pd.to_datetime(frame[date_col], errors='coerce'),
        'value': pd.to_numeric(frame[value_col], errors='coerce'),
    }).dropna()
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
    return result[result['date'] >= cutoff]


def get_us_bond_history(tenor='10Y', years=5):
    series = US_BOND_SERIES.get(tenor, 'DGS10')
    return _cached(
        f'us-bond-history:{series}:{years}', 1800,
        lambda: _fred_history(series, years),
    )


def _find_kr_item(tenor):
    korean = tenor.replace('Y', '년')
    for code, name in _ecos_items():
        compact = name.replace(' ', '')
        if '국고채' in compact and korean in compact:
            return code, name
    return None, f'국고채({korean})'


def get_kr_bond_history(tenor='10Y', years=5):
    def load():
        code, name = _find_kr_item(tenor)
        if not code:
            return pd.DataFrame(columns=['date', 'value'])
        key = _ecos_key()
        today = datetime.now(ZoneInfo('Asia/Seoul')).date()
        start = today - timedelta(days=int(365.25 * years) + 20)
        url = (
            f'https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/10000/'
            f'817Y002/D/{start:%Y%m%d}/{today:%Y%m%d}/{code}/'
        )
        response = requests.get(url, timeout=12)
        response.raise_for_status()
        rows = (response.json().get('StatisticSearch') or {}).get('row') or []
        data = []
        for row in rows:
            try:
                data.append({
                    'date': pd.to_datetime(row.get('TIME'), format='%Y%m%d', errors='coerce'),
                    'value': float(row.get('DATA_VALUE')),
                })
            except Exception:
                pass
        return pd.DataFrame(data).dropna().sort_values('date') if data else pd.DataFrame(columns=['date','value'])
    return _cached(f'kr-bond-history:{tenor}:{years}', 1800, load)


def get_us_spread_history(spread='10Y-2Y', years=10):
    mapping = {'10Y-2Y': 'T10Y2Y', '10Y-3M': 'T10Y3M'}
    series = mapping.get(spread, 'T10Y2Y')
    return _cached(
        f'us-spread:{series}:{years}', 1800,
        lambda: _fred_history(series, years),
    )


def line_chart_options(frame, title, suffix='%'):
    if frame is None or frame.empty:
        return None
    labels = [d.strftime('%Y-%m-%d') for d in pd.to_datetime(frame['date'])]
    values = [round(float(v), 4) for v in frame['value']]
    return {
        'animation': False,
        'backgroundColor': 'transparent',
        'title': {'text': title, 'left': 12, 'top': 8, 'textStyle': {'color': '#e2e8f0', 'fontSize': 15}},
        'tooltip': {'trigger': 'axis'},
        'grid': {'left': 58, 'right': 22, 'top': 52, 'bottom': 50},
        'xAxis': {
            'type': 'category', 'data': labels,
            'axisLabel': {'color': '#64748b', 'hideOverlap': True},
            'axisLine': {'lineStyle': {'color': '#334155'}},
        },
        'yAxis': {
            'type': 'value', 'scale': True,
            'axisLabel': {'color': '#64748b', 'formatter': '{value}' + suffix},
            'splitLine': {'lineStyle': {'color': 'rgba(100,116,139,.13)'}},
        },
        'dataZoom': [
            {'type': 'inside', 'start': 0, 'end': 100},
            {'type': 'slider', 'bottom': 8, 'height': 17, 'borderColor': 'transparent'},
        ],
        'series': [{
            'type': 'line', 'data': values, 'showSymbol': False,
            'smooth': False, 'lineStyle': {'width': 2}, 'areaStyle': {'opacity': .05},
        }],
    }

# ---------------------------------------------------------------------------
# v1.2 robust Korea bond data + historical yield-curve snapshots
# ---------------------------------------------------------------------------

KR_BOND_STATIC = {
    # Stable ECOS 817Y002 item codes documented in long-running ECOS examples.
    "1Y": ("010190000", "국고채(1년)"),
    "3Y": ("010200000", "국고채(3년)"),
    "5Y": ("010200001", "국고채(5년)"),
    "10Y": ("010210000", "국고채(10년)"),
    "20Y": ("010220000", "국고채(20년)"),
}


def _ecos_stat_search(item_code=None, start=None, end=None, page_size=1000):
    """Fetch ECOS 817Y002 with pagination.

    `StatisticItemList` is not reliably available with the public `sample` key,
    while `StatisticSearch` is. Therefore v1.2 discovers unknown tenors from
    actual recent observations and uses stable static codes where known.
    """
    key = _ecos_key()
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    end = end or today
    start = start or (end - timedelta(days=45))

    def url_for(a, b):
        base = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/{a}/{b}/"
            f"817Y002/D/{start:%Y%m%d}/{end:%Y%m%d}"
        )
        if item_code:
            base += f"/{item_code}"
        return base

    first = requests.get(url_for(1, page_size), timeout=12)
    first.raise_for_status()
    body = first.json()
    block = body.get("StatisticSearch") or {}
    rows = list(block.get("row") or [])
    total = int(block.get("list_total_count") or len(rows))

    for offset in range(page_size + 1, total + 1, page_size):
        last = min(offset + page_size - 1, total)
        response = requests.get(url_for(offset, last), timeout=12)
        response.raise_for_status()
        rows.extend((response.json().get("StatisticSearch") or {}).get("row") or [])
    return rows


def _kr_item_map():
    cached = _CACHE.get("kr-item-map-v12")
    if cached and time.time() - cached[0] < 86400:
        return cached[1]

    mapping = dict(KR_BOND_STATIC)
    try:
        rows = _ecos_stat_search(start=datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=20))
        for row in rows:
            code = str(row.get("ITEM_CODE1") or "")
            name = str(row.get("ITEM_NAME1") or "").replace(" ", "")
            for tenor in ("1", "2", "3", "5", "10", "20", "30"):
                if f"국고채({tenor}년)" in name and code:
                    mapping[f"{tenor}Y"] = (code, row.get("ITEM_NAME1") or f"국고채({tenor}년)")
    except Exception:
        pass

    _CACHE["kr-item-map-v12"] = (time.time(), mapping)
    return mapping


def _kr_item(tenor):
    return _kr_item_map().get(tenor, (None, f"국고채({tenor.replace('Y', '년')})"))


def get_kr_bond_history(tenor="10Y", years=5):
    def load():
        code, _ = _kr_item(tenor)
        if not code:
            return pd.DataFrame(columns=["date", "value"])
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        start = today - timedelta(days=int(365.25 * years) + 45)
        try:
            rows = _ecos_stat_search(code, start=start, end=today)
        except Exception:
            return pd.DataFrame(columns=["date", "value"])

        data = []
        for row in rows:
            try:
                data.append(
                    {
                        "date": pd.to_datetime(row.get("TIME"), format="%Y%m%d", errors="coerce"),
                        "value": float(row.get("DATA_VALUE")),
                    }
                )
            except Exception:
                pass
        if not data:
            return pd.DataFrame(columns=["date", "value"])
        return pd.DataFrame(data).dropna().drop_duplicates("date").sort_values("date")

    return _cached(f"kr-bond-history-v12:{tenor}:{years}", 1800, load)


def get_kr_yield_curve():
    def load():
        result = []
        for tenor in ("1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y"):
            code, name = _kr_item(tenor)
            value = None
            if code:
                try:
                    frame = get_kr_bond_history(tenor, 1)
                    if not frame.empty:
                        value = float(frame["value"].iloc[-1])
                except Exception:
                    pass
            result.append({"tenor": tenor, "value": value, "name": name, "series": code})
        return result

    return _cached("kr-curve-v12", 1200, load)


def _value_on_or_before(frame, target_date):
    if frame is None or frame.empty:
        return None
    target = pd.Timestamp(target_date).tz_localize(None)
    dates = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    subset = frame[dates <= target]
    if subset.empty:
        return None
    return float(subset["value"].iloc[-1])


def get_us_curve_snapshots():
    """Current, 1M, 3M and 1Y ago US Treasury curves."""
    def load():
        today = datetime.now(ZoneInfo("America/New_York")).date()
        offsets = [("현재", 0), ("1개월 전", 30), ("3개월 전", 90), ("1년 전", 365)]
        histories = {tenor: _fred_history(series, 2) for series, tenor in US_TREASURY}
        snapshots = []
        for label, days in offsets:
            target = today - timedelta(days=days)
            points = []
            for _, tenor in US_TREASURY:
                points.append({"tenor": tenor, "value": _value_on_or_before(histories[tenor], target)})
            snapshots.append({"label": label, "date": target.isoformat(), "points": points})
        return snapshots
    return _cached("us-curve-snapshots-v12", 1800, load)


def get_kr_curve_snapshots():
    """Current, 1M, 3M and 1Y ago Korean Treasury curves."""
    def load():
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        offsets = [("현재", 0), ("1개월 전", 30), ("3개월 전", 90), ("1년 전", 365)]
        tenors = ("1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y")
        histories = {tenor: get_kr_bond_history(tenor, 2) for tenor in tenors}
        snapshots = []
        for label, days in offsets:
            target = today - timedelta(days=days)
            points = []
            for tenor in tenors:
                points.append({"tenor": tenor, "value": _value_on_or_before(histories[tenor], target)})
            snapshots.append({"label": label, "date": target.isoformat(), "points": points})
        return snapshots
    return _cached("kr-curve-snapshots-v12", 1800, load)


def get_kr_spread_history(spread="10Y-2Y", years=5):
    if spread != "10Y-2Y":
        return pd.DataFrame(columns=["date", "value"])
    left = get_kr_bond_history("10Y", years)
    right = get_kr_bond_history("2Y", years)
    if left.empty or right.empty:
        return pd.DataFrame(columns=["date", "value"])
    merged = pd.merge(left, right, on="date", how="inner", suffixes=("_10y", "_2y"))
    merged["value"] = merged["value_10y"] - merged["value_2y"]
    return merged[["date", "value"]]


def curve_compare_options(snapshots, title):
    if not snapshots:
        return None
    categories = [p["tenor"] for p in snapshots[0].get("points", [])]
    series = []
    for snap in snapshots:
        series.append(
            {
                "name": f"{snap['label']} ({snap['date']})",
                "type": "line",
                "smooth": True,
                "symbolSize": 7,
                "connectNulls": False,
                "data": [p.get("value") for p in snap.get("points", [])],
            }
        )
    return {
        "animation": False,
        "backgroundColor": "transparent",
        "title": {"text": title, "left": 12, "top": 8, "textStyle": {"color": "#e2e8f0", "fontSize": 15}},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 34, "textStyle": {"color": "#94a3b8"}},
        "grid": {"left": 55, "right": 22, "top": 82, "bottom": 42},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"color": "#94a3b8"}},
        "yAxis": {
            "type": "value",
            "scale": True,
            "axisLabel": {"formatter": "{value}%", "color": "#94a3b8"},
            "splitLine": {"lineStyle": {"color": "rgba(100,116,139,.13)"}},
        },
        "series": series,
    }
