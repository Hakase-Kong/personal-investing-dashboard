import time
from threading import Lock

import pandas as pd
import yfinance as yf

_CACHE = {}
_LOCK = Lock()


def _cached(key, ttl, loader):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1].copy()
    value = loader()
    with _LOCK:
        _CACHE[key] = (now, value.copy())
    return value


def _kr_symbol(exchange, symbol):
    return f"{symbol}.KQ" if "KOSDAQ" in str(exchange).upper() else f"{symbol}.KS"


def _f(value):
    try:
        return None if value in (None, "") else float(value)
    except Exception:
        return None


def _clean(df):
    if df.empty:
        return df
    return (
        df.dropna(subset=["date", "open", "high", "low", "close"])
        .sort_values("date")
        .drop_duplicates("date", keep="last")
    )


def _kis_period(kis, symbol, period):
    rows = kis.get_domestic_period_chart(symbol, period, pages=2)
    data = []
    for row in rows:
        date = row.get("stck_bsop_date")
        if not date:
            continue
        data.append({
            "date": pd.to_datetime(date, format="%Y%m%d", errors="coerce"),
            "open": _f(row.get("stck_oprc")),
            "high": _f(row.get("stck_hgpr")),
            "low": _f(row.get("stck_lwpr")),
            "close": _f(row.get("stck_clpr")),
            "volume": _f(row.get("acml_vol")) or 0,
        })
    return _clean(pd.DataFrame(data))


def _kis_intraday(kis, symbol):
    rows = kis.get_domestic_intraday_chart(symbol)
    data = []
    for row in rows:
        date = row.get("stck_bsop_date")
        hour = row.get("stck_cntg_hour")
        if not date or not hour:
            continue
        data.append({
            "date": pd.to_datetime(
                f"{date}{hour}", format="%Y%m%d%H%M%S", errors="coerce"
            ),
            "open": _f(row.get("stck_oprc")),
            "high": _f(row.get("stck_hgpr")),
            "low": _f(row.get("stck_lwpr")),
            "close": _f(row.get("stck_prpr")),
            "volume": _f(row.get("cntg_vol")) or 0,
        })
    return _clean(pd.DataFrame(data))


def _yf(symbol, period, interval):
    frame = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if frame.empty:
        return pd.DataFrame()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.reset_index()
    date_col = "Datetime" if "Datetime" in frame.columns else "Date"
    return _clean(pd.DataFrame({
        "date": pd.to_datetime(frame[date_col]),
        "open": pd.to_numeric(frame["Open"], errors="coerce"),
        "high": pd.to_numeric(frame["High"], errors="coerce"),
        "low": pd.to_numeric(frame["Low"], errors="coerce"),
        "close": pd.to_numeric(frame["Close"], errors="coerce"),
        "volume": pd.to_numeric(frame["Volume"], errors="coerce").fillna(0),
    }))


def get_chart_df(kis, market, exchange, symbol, timeframe):
    key = (market, exchange, symbol, timeframe)

    if market == "KR":
        if timeframe == "1D":
            def load_intraday():
                try:
                    df = _kis_intraday(kis, symbol)
                    if not df.empty:
                        return df
                except Exception:
                    pass
                return _yf(_kr_symbol(exchange, symbol), "1d", "1m")
            return _cached(key, 45, load_intraday)

        code = {"D": "D", "W": "W", "M": "M"}.get(timeframe, "D")

        def load_period():
            try:
                df = _kis_period(kis, symbol, code)
                if not df.empty:
                    return df
            except Exception:
                pass
            period, interval = {
                "D": ("2y", "1d"),
                "W": ("5y", "1wk"),
                "M": ("10y", "1mo"),
            }[timeframe]
            return _yf(_kr_symbol(exchange, symbol), period, interval)

        ttl = {"D": 600, "W": 1800, "M": 3600}[timeframe]
        return _cached(key, ttl, load_period)

    period, interval, ttl = {
        "1D": ("1d", "1m", 45),
        "D": ("2y", "1d", 600),
        "W": ("5y", "1wk", 1800),
        "M": ("10y", "1mo", 3600),
    }.get(timeframe, ("2y", "1d", 600))
    return _cached(key, ttl, lambda: _yf(symbol, period, interval))


def _ma(values, window):
    series = pd.Series(values, dtype="float64")
    ma = series.rolling(window).mean()
    return [None if pd.isna(v) else round(float(v), 4) for v in ma]


def get_echart_options(
    kis,
    market,
    exchange,
    symbol,
    timeframe="D",
    moving_averages=(5, 20, 60, 120),
):
    df = get_chart_df(kis, market, exchange, symbol, timeframe)
    if df.empty:
        raise RuntimeError("표시할 차트 데이터가 없습니다.")

    # Keep enough information but avoid sending unnecessarily huge payloads.
    if timeframe == "1D":
        df = df.tail(420)
    else:
        df = df.tail(260)

    labels = [
        d.strftime("%H:%M") if timeframe == "1D" else d.strftime("%Y-%m-%d")
        for d in pd.to_datetime(df["date"])
    ]
    closes = [round(float(v), 4) for v in df["close"]]
    candles = [
        [
            round(float(row.open), 4),
            round(float(row.close), 4),
            round(float(row.low), 4),
            round(float(row.high), 4),
        ]
        for row in df.itertuples()
    ]
    volumes = [round(float(v), 2) for v in df["volume"]]

    series = [
        {
            "name": symbol,
            "type": "candlestick",
            "data": candles,
            "itemStyle": {
                "color": "#ef4444",
                "color0": "#3b82f6",
                "borderColor": "#ef4444",
                "borderColor0": "#3b82f6",
            },
        }
    ]

    for window in moving_averages:
        series.append({
            "name": f"MA{int(window)}",
            "type": "line",
            "data": _ma(closes, int(window)),
            "showSymbol": False,
            "smooth": False,
            "lineStyle": {"width": 1.3},
            "connectNulls": False,
        })

    series.append({
        "name": "Volume",
        "type": "bar",
        "xAxisIndex": 1,
        "yAxisIndex": 1,
        "data": volumes,
        "itemStyle": {"color": "rgba(148,163,184,.42)"},
    })

    return {
        "animation": False,
        "backgroundColor": "transparent",
        "legend": {
            "top": 6,
            "left": 12,
            "textStyle": {"color": "#94a3b8"},
        },
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
        "axisPointer": {"link": [{"xAxisIndex": "all"}]},
        "grid": [
            {"left": 58, "right": 20, "top": 52, "height": "61%"},
            {"left": 58, "right": 20, "top": "78%", "height": "14%"},
        ],
        "xAxis": [
            {
                "type": "category",
                "data": labels,
                "boundaryGap": True,
                "axisLine": {"lineStyle": {"color": "#334155"}},
                "axisLabel": {"color": "#64748b", "hideOverlap": True},
                "splitLine": {"show": False},
            },
            {
                "type": "category",
                "gridIndex": 1,
                "data": labels,
                "boundaryGap": True,
                "axisLine": {"lineStyle": {"color": "#334155"}},
                "axisLabel": {"show": False},
                "splitLine": {"show": False},
            },
        ],
        "yAxis": [
            {
                "scale": True,
                "axisLabel": {"color": "#64748b"},
                "splitLine": {"lineStyle": {"color": "rgba(100,116,139,.13)"}},
            },
            {
                "scale": True,
                "gridIndex": 1,
                "axisLabel": {"color": "#64748b"},
                "splitLine": {"show": False},
            },
        ],
        "dataZoom": [
            {"type": "inside", "xAxisIndex": [0, 1], "start": 35, "end": 100},
            {
                "type": "slider",
                "xAxisIndex": [0, 1],
                "bottom": 8,
                "height": 18,
                "borderColor": "transparent",
                "backgroundColor": "rgba(15,23,42,.2)",
                "fillerColor": "rgba(59,130,246,.15)",
            },
        ],
        "series": series,
    }
