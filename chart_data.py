import time
from threading import Lock
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from plotly.subplots import make_subplots

_CACHE = {}
_LOCK = Lock()

def _cached(key, ttl, loader):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now-hit[0] < ttl:
            return hit[1].copy()
    value = loader()
    with _LOCK:
        _CACHE[key] = (now,value.copy())
    return value

def _kr_symbol(exchange,symbol):
    return f"{symbol}.KQ" if "KOSDAQ" in exchange.upper() else f"{symbol}.KS"

def _clean(df):
    if df.empty: return df
    return df.dropna(
        subset=["date","open","high","low","close"]
    ).sort_values("date")

def _f(v):
    try: return None if v in (None,"") else float(v)
    except Exception: return None

def _kis_period(kis,symbol,period):
    rows = kis.get_domestic_period_chart(symbol,period,2)
    data = []
    for r in rows:
        d=r.get("stck_bsop_date")
        if d:
            data.append({
                "date":pd.to_datetime(d,format="%Y%m%d",errors="coerce"),
                "open":_f(r.get("stck_oprc")),
                "high":_f(r.get("stck_hgpr")),
                "low":_f(r.get("stck_lwpr")),
                "close":_f(r.get("stck_clpr")),
                "volume":_f(r.get("acml_vol")) or 0,
            })
    return _clean(pd.DataFrame(data))

def _kis_intraday(kis,symbol):
    rows=kis.get_domestic_intraday_chart(symbol)
    data=[]
    for r in rows:
        d,t=r.get("stck_bsop_date"),r.get("stck_cntg_hour")
        if d and t:
            data.append({
                "date":pd.to_datetime(f"{d}{t}",format="%Y%m%d%H%M%S",errors="coerce"),
                "open":_f(r.get("stck_oprc")),
                "high":_f(r.get("stck_hgpr")),
                "low":_f(r.get("stck_lwpr")),
                "close":_f(r.get("stck_prpr")),
                "volume":_f(r.get("cntg_vol")) or 0,
            })
    return _clean(pd.DataFrame(data))

def _yf(symbol,period,interval):
    f=yf.download(
        symbol,period=period,interval=interval,
        auto_adjust=False,progress=False,threads=False,
    )
    if f.empty:return pd.DataFrame()
    if isinstance(f.columns,pd.MultiIndex):
        f.columns=f.columns.get_level_values(0)
    f=f.reset_index()
    dc="Datetime" if "Datetime" in f.columns else "Date"
    return _clean(pd.DataFrame({
        "date":pd.to_datetime(f[dc]),
        "open":pd.to_numeric(f["Open"],errors="coerce"),
        "high":pd.to_numeric(f["High"],errors="coerce"),
        "low":pd.to_numeric(f["Low"],errors="coerce"),
        "close":pd.to_numeric(f["Close"],errors="coerce"),
        "volume":pd.to_numeric(f["Volume"],errors="coerce").fillna(0),
    }))

def get_chart_df(kis,market,exchange,symbol,timeframe):
    key=(market,exchange,symbol,timeframe)
    if market=="KR":
        if timeframe=="1D":
            def load():
                try:
                    d=_kis_intraday(kis,symbol)
                    if not d.empty:return d
                except Exception: pass
                return _yf(_kr_symbol(exchange,symbol),"1d","1m")
            return _cached(key,60,load)
        code={"D":"D","W":"W","M":"M"}.get(timeframe,"D")
        def load():
            try:
                d=_kis_period(kis,symbol,code)
                if not d.empty:return d
            except Exception: pass
            p,i={"D":("2y","1d"),"W":("5y","1wk"),"M":("10y","1mo")}[timeframe]
            return _yf(_kr_symbol(exchange,symbol),p,i)
        return _cached(key,300,load)
    p,i,ttl={
        "1D":("1d","1m",60),
        "D":("2y","1d",300),
        "W":("5y","1wk",600),
        "M":("10y","1mo",900),
    }.get(timeframe,("2y","1d",300))
    return _cached(key,ttl,lambda:_yf(symbol,p,i))

def get_chart_figure(kis,market,exchange,symbol,timeframe,moving_averages=(5,20,60,120)):
    df=get_chart_df(kis,market,exchange,symbol,timeframe)
    if df.empty:
        raise RuntimeError("표시할 차트 데이터가 없습니다.")
    df=df.sort_values("date").drop_duplicates("date",keep="last")
    for w in moving_averages:
        df[f"ma{int(w)}"]=df["close"].rolling(int(w)).mean()

    fig=make_subplots(
        rows=2,cols=1,shared_xaxes=True,
        vertical_spacing=.04,row_heights=[.76,.24],
    )
    fig.add_trace(go.Candlestick(
        x=df["date"],open=df["open"],high=df["high"],
        low=df["low"],close=df["close"],name=symbol,
    ),row=1,col=1)
    for w in moving_averages:
        fig.add_trace(go.Scatter(
            x=df["date"],y=df[f"ma{int(w)}"],
            mode="lines",name=f"MA{int(w)}",
            line={"width":1.4},
        ),row=1,col=1)
    fig.add_trace(go.Bar(
        x=df["date"],y=df["volume"],name="Volume",opacity=.65
    ),row=2,col=1)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f141c",
        plot_bgcolor="#0f141c",
        margin={"l":18,"r":18,"t":45,"b":20},
        height=610,
        legend={"orientation":"h","y":1.01,"x":0},
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        title={"text":f"{symbol} · {timeframe}","x":.01},
    )
    fig.update_xaxes(showgrid=False,rangeslider_visible=False)
    fig.update_yaxes(gridcolor="rgba(148,163,184,.10)",zeroline=False)
    return fig
