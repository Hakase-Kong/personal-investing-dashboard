import time
from io import StringIO
from threading import Lock
import pandas as pd
import requests
import yfinance as yf

_CACHE={}
_LOCK=Lock()

MARKETS=[
    ("^KS11","KOSPI",""),
    ("^KQ11","KOSDAQ",""),
    ("^GSPC","S&P 500",""),
    ("^IXIC","NASDAQ",""),
    ("^VIX","VIX",""),
    ("KRW=X","USD/KRW","₩"),
    ("^TNX","US 10Y","%"),
]
FRED_SERIES=[
    ("DGS10","미국 10년물","%","last"),
    ("FEDFUNDS","Fed Funds","%","last"),
    ("CPIAUCSL","미국 CPI YoY","%","yoy"),
    ("UNRATE","미국 실업률","%","last"),
]

def _cached(key,ttl,loader):
    now=time.time()
    with _LOCK:
        hit=_CACHE.get(key)
        if hit and now-hit[0]<ttl:return hit[1]
    val=loader()
    with _LOCK:_CACHE[key]=(now,val)
    return val

def _hist(symbol,period="5d",interval="1d"):
    f=yf.download(symbol,period=period,interval=interval,progress=False,auto_adjust=False,threads=False)
    if f.empty:return pd.DataFrame()
    if isinstance(f.columns,pd.MultiIndex):f.columns=f.columns.get_level_values(0)
    return f

def get_market_overview():
    def load():
        out=[]
        for s,n,suffix in MARKETS:
            try:
                f=_hist(s)
                c=pd.to_numeric(f["Close"],errors="coerce").dropna()
                last=float(c.iloc[-1]); prev=float(c.iloc[-2]) if len(c)>1 else last
                ch=last-prev; pct=ch/prev*100 if prev else 0
                out.append({"symbol":s,"name":n,"value":last,"change":ch,"percent":pct,"suffix":suffix})
            except Exception:
                out.append({"symbol":s,"name":n,"value":None,"change":None,"percent":None,"suffix":suffix})
        return out
    return _cached("markets",60,load)

def _fred(series):
    r=requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}",timeout=10)
    r.raise_for_status()
    f=pd.read_csv(StringIO(r.text))
    col=f.columns[-1]
    f[col]=pd.to_numeric(f[col],errors="coerce")
    return f.dropna(subset=[col])[col].astype(float).tolist()

def get_macro_overview():
    def load():
        out=[]
        for sid,name,suffix,mode in FRED_SERIES:
            try:
                v=_fred(sid)
                if mode=="yoy":
                    value=(v[-1]/v[-13]-1)*100
                    prev=(v[-2]/v[-14]-1)*100 if len(v)>=14 else value
                else:
                    value=v[-1]; prev=v[-2] if len(v)>1 else value
                out.append({"id":sid,"name":name,"value":value,"change":value-prev,"suffix":suffix})
            except Exception:
                out.append({"id":sid,"name":name,"value":None,"change":None,"suffix":suffix})
        return out
    return _cached("macro",900,load)

def _news_item(raw,label):
    content=raw.get("content") if isinstance(raw,dict) else None
    src=content if isinstance(content,dict) else raw
    if not isinstance(src,dict):return None
    title=src.get("title")
    if not title:return None
    provider=src.get("provider")
    pub=provider.get("displayName","") if isinstance(provider,dict) else src.get("publisher","")
    url=""
    for key in ("canonicalUrl","clickThroughUrl"):
        x=src.get(key)
        if isinstance(x,dict) and x.get("url"):url=x["url"];break
    url=url or src.get("link") or src.get("url") or ""
    return {"title":str(title),"publisher":str(pub),"url":str(url),"symbol":label}

def get_watchlist_news(items,limit=10):
    syms=[]
    for i in items:
        s=i.get("symbol","")
        if i.get("market")=="KR":
            s=f"{s}.KQ" if "KOSDAQ" in str(i.get("exchange","")).upper() else f"{s}.KS"
        if s:syms.append((s,i.get("name") or i.get("symbol")))
    def load():
        out=[];seen=set()
        for s,label in syms[:8]:
            try:
                for raw in (yf.Ticker(s).news or [])[:6]:
                    item=_news_item(raw,label)
                    if not item:continue
                    k=item["title"].lower()
                    if k in seen:continue
                    seen.add(k);out.append(item)
                    if len(out)>=limit:return out
            except Exception:pass
        return out
    return _cached("news:"+",".join(s for s,_ in syms[:8]),300,load)

def get_sparkline_svg(market,exchange,symbol,width=300,height=74):
    from public_data import sparkline_svg
    ys=symbol
    if market=="KR":
        ys=f"{symbol}.KQ" if "KOSDAQ" in str(exchange).upper() else f"{symbol}.KS"
    def load():
        try:
            f=_hist(ys,"2mo","1d")
            vals=pd.to_numeric(f["Close"],errors="coerce").dropna().tail(30).tolist()
            return sparkline_svg(vals,width,height)
        except Exception:return ""
    return _cached(f"spark:{market}:{exchange}:{symbol}",600,load)
