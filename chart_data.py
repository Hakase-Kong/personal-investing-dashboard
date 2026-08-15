import time
from datetime import datetime
from threading import Lock

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from plotly.subplots import make_subplots

_CACHE = {}
_CACHE_LOCK = Lock()


def _cached(key, ttl, loader):
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1].copy()

    value = loader()

    with _CACHE_LOCK:
        _CACHE[key] = (now, value.copy())

    return value


def _kr_yahoo_symbol(exchange: str, symbol: str) -> str:
    return f"{symbol}.KQ" if "KOSDAQ" in exchange.upper() else f"{symbol}.KS"


def _kis_period_df(kis, symbol, period):
    rows = kis.get_domestic_period_chart(
        symbol,
        period=period,
        pages=2,
    )
    data = []

    for row in rows:
        d = row.get("stck_bsop_date")
        if not d:
            continue
        data.append(
            {
                "date": pd.to_datetime(d, format="%Y%m%d", errors="coerce"),
                "open": _f(row.get("stck_oprc")),
                "high": _f(row.get("stck_hgpr")),
                "low": _f(row.get("stck_lwpr")),
                "close": _f(row.get("stck_clpr")),
                "volume": _f(row.get("acml_vol")) or 0,
            }
        )

    return _clean_df(pd.DataFrame(data))


def _kis_intraday_df(kis, symbol):
    rows = kis.get_domestic_intraday_chart(symbol)
    data = []

    for row in rows:
        d = row.get("stck_bsop_date")
        t = row.get("stck_cntg_hour")
        if not d or not t:
            continue

        dt = pd.to_datetime(
            f"{d}{t}",
            format="%Y%m%d%H%M%S",
            errors="coerce",
        )
        data.append(
            {
                "date": dt,
                "open": _f(row.get("stck_oprc")),
                "high": _f(row.get("stck_hgpr")),
                "low": _f(row.get("stck_lwpr")),
                "close": _f(row.get("stck_prpr")),
                "volume": _f(row.get("cntg_vol")) or 0,
            }
        )

    return _clean_df(pd.DataFrame(data))


def _yf_df(symbol, period, interval):
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

    data = pd.DataFrame(
        {
            "date": pd.to_datetime(frame[date_col]),
            "open": pd.to_numeric(frame["Open"], errors="coerce"),
            "high": pd.to_numeric(frame["High"], errors="coerce"),
            "low": pd.to_numeric(frame["Low"], errors="coerce"),
            "close": pd.to_numeric(frame["Close"], errors="coerce"),
            "volume": pd.to_numeric(frame["Volume"], errors="coerce").fillna(0),
        }
    )
    return _clean_df(data)


def get_chart_df(kis, market, exchange, symbol, timeframe):
    cache_key = (market, exchange, symbol, timeframe)

    if market == "KR":
        if timeframe == "1D":
            def load_intraday():
                try:
                    df = _kis_intraday_df(kis, symbol)
                    if not df.empty:
                        return df
                except Exception:
                    pass
                return _yf_df(
                    _kr_yahoo_symbol(exchange, symbol),
                    "1d",
                    "1m",
                )

            return _cached(cache_key, 60, load_intraday)

        period_code = {
            "D": "D",
            "W": "W",
            "M": "M",
        }.get(timeframe, "D")

        def load_period():
            try:
                df = _kis_period_df(kis, symbol, period_code)
                if not df.empty:
                    return df
            except Exception:
                pass

            yf_symbol = _kr_yahoo_symbol(exchange, symbol)
            fallback = {
                "D": ("2y", "1d"),
                "W": ("5y", "1wk"),
                "M": ("10y", "1mo"),
            }[timeframe]
            return _yf_df(yf_symbol, *fallback)

        return _cached(cache_key, 300, load_period)

    mapping = {
        "1D": ("1d", "1m", 60),
        "D": ("2y", "1d", 300),
        "W": ("5y", "1wk", 600),
        "M": ("10y", "1mo", 900),
    }
    period, interval, ttl = mapping.get(
        timeframe,
        ("2y", "1d", 300),
    )
    return _cached(
        cache_key,
        ttl,
        lambda: _yf_df(symbol, period, interval),
    )


def get_chart_figure(
    kis,
    market,
    exchange,
    symbol,
    timeframe,
    moving_averages=(5, 20, 60, 120),
):
    df = get_chart_df(
        kis,
        market,
        exchange,
        symbol,
        timeframe,
    )

    if df.empty:
        raise RuntimeError("표시할 차트 데이터가 없습니다.")

    df = df.sort_values("date").drop_duplicates(
        subset=["date"],
        keep="last",
    )

    for window in moving_averages:
        df[f"ma{int(window)}"] = (
            df["close"]
            .rolling(int(window))
            .mean()
        )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.76, 0.24],
    )

    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=symbol,
        ),
        row=1,
        col=1,
    )

    for window in moving_averages:
        col = f"ma{int(window)}"
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df["date"],
                    y=df[col],
                    mode="lines",
                    name=f"MA{int(window)}",
                    line={"width": 1.4},
                ),
                row=1,
                col=1,
            )

    fig.add_trace(
        go.Bar(
            x=df["date"],
            y=df["volume"],
            name="Volume",
            opacity=0.65,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f141c",
        plot_bgcolor="#0f141c",
        margin={"l": 18, "r": 18, "t": 45, "b": 20},
        height=610,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.01,
            "xanchor": "left",
            "x": 0,
        },
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        title={
            "text": f"{symbol} · {timeframe}",
            "x": 0.01,
        },
    )

    fig.update_xaxes(
        showgrid=False,
        rangeslider_visible=False,
    )
    fig.update_yaxes(
        gridcolor="rgba(148,163,184,.10)",
        zeroline=False,
    )

    return fig


def _clean_df(df):
    if df.empty:
        return df
    df = df.dropna(
        subset=["date", "open", "high", "low", "close"]
    )
    return df.sort_values("date")


def _f(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
