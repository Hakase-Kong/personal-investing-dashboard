import time
from threading import Lock
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from plotly.subplots import make_subplots
_CACHE={};_LOCK=Lock()

def _cached(k,ttl,loader):
    now=time.time()
    with _LOCK:
        h=_CACHE.get(k)
        if h and now-h[0]<ttl:return h[1].copy()
    v=loader()
    with _LOCK:_CACHE[k]=(now,v.copy())
    return v
def _kr(e,s):return f"{s}.KQ" if "KOSDAQ" in e.upper() else f"{s}.KS"
def _f(v):
    try:return None if v in (None,"") else float(v)
    except Exception:return None
def _clean(d):
    if d.empty:return d
    return d.dropna(subset=["date","open","high","low","close"]).sort_values("date")
def _kp(kis,s,p):
    rows=kis.get_domestic_period_chart(s,p,2);d=[]
    for r in rows:
        x=r.get("stck_bsop_date")
        if x:d.append({"date":pd.to_datetime(x,format="%Y%m%d",errors="coerce"),
        "open":_f(r.get("stck_oprc")),"high":_f(r.get("stck_hgpr")),
        "low":_f(r.get("stck_lwpr")),"close":_f(r.get("stck_clpr")),"volume":_f(r.get("acml_vol")) or 0})
    return _clean(pd.DataFrame(d))
def _ki(kis,s):
    rows=kis.get_domestic_intraday_chart(s);d=[]
    for r in rows:
        x,t=r.get("stck_bsop_date"),r.get("stck_cntg_hour")
        if x and t:d.append({"date":pd.to_datetime(f"{x}{t}",format="%Y%m%d%H%M%S",errors="coerce"),
        "open":_f(r.get("stck_oprc")),"high":_f(r.get("stck_hgpr")),
        "low":_f(r.get("stck_lwpr")),"close":_f(r.get("stck_prpr")),"volume":_f(r.get("cntg_vol")) or 0})
    return _clean(pd.DataFrame(d))
def _yf(s,p,i):
    f=yf.download(s,period=p,interval=i,auto_adjust=False,progress=False,threads=False)
    if f.empty:return pd.DataFrame()
    if isinstance(f.columns,pd.MultiIndex):f.columns=f.columns.get_level_values(0)
    f=f.reset_index();dc="Datetime" if "Datetime" in f.columns else "Date"
    return _clean(pd.DataFrame({"date":pd.to_datetime(f[dc]),"open":pd.to_numeric(f["Open"],errors="coerce"),
    "high":pd.to_numeric(f["High"],errors="coerce"),"low":pd.to_numeric(f["Low"],errors="coerce"),
    "close":pd.to_numeric(f["Close"],errors="coerce"),"volume":pd.to_numeric(f["Volume"],errors="coerce").fillna(0)}))
def get_chart_df(kis,m,e,s,t):
    k=(m,e,s,t)
    if m=="KR":
        if t=="1D":
            def load():
                try:
                    d=_ki(kis,s)
                    if not d.empty:return d
                except Exception:pass
                return _yf(_kr(e,s),"1d","1m")
            return _cached(k,60,load)
        code={"D":"D","W":"W","M":"M"}.get(t,"D")
        def load():
            try:
                d=_kp(kis,s,code)
                if not d.empty:return d
            except Exception:pass
            p,i={"D":("2y","1d"),"W":("5y","1wk"),"M":("10y","1mo")}[t]
            return _yf(_kr(e,s),p,i)
        return _cached(k,300,load)
    p,i,ttl={"1D":("1d","1m",60),"D":("2y","1d",300),"W":("5y","1wk",600),"M":("10y","1mo",900)}.get(t,("2y","1d",300))
    return _cached(k,ttl,lambda:_yf(s,p,i))
def get_chart_figure(kis,m,e,s,t,moving_averages=(5,20,60,120)):
    d=get_chart_df(kis,m,e,s,t)
    if d.empty:raise RuntimeError("표시할 차트 데이터가 없습니다.")
    d=d.sort_values("date").drop_duplicates("date",keep="last")
    for w in moving_averages:d[f"ma{int(w)}"]=d["close"].rolling(int(w)).mean()
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.04,row_heights=[.76,.24])
    fig.add_trace(go.Candlestick(x=d["date"],open=d["open"],high=d["high"],low=d["low"],close=d["close"],name=s),row=1,col=1)
    for w in moving_averages:
        fig.add_trace(go.Scatter(x=d["date"],y=d[f"ma{int(w)}"],mode="lines",name=f"MA{int(w)}",line={"width":1.4}),row=1,col=1)
    fig.add_trace(go.Bar(x=d["date"],y=d["volume"],name="Volume",opacity=.65),row=2,col=1)
    fig.update_layout(template="plotly_dark",paper_bgcolor="#0f141c",plot_bgcolor="#0f141c",
        margin={"l":18,"r":18,"t":45,"b":20},height=610,legend={"orientation":"h","y":1.01,"x":0},
        xaxis_rangeslider_visible=False,hovermode="x unified",title={"text":f"{s} · {t}","x":.01})
    fig.update_xaxes(showgrid=False,rangeslider_visible=False);fig.update_yaxes(gridcolor="rgba(148,163,184,.10)",zeroline=False)
    return fig
