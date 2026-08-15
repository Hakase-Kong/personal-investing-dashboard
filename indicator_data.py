import time
from io import StringIO
from threading import Lock
import pandas as pd
import plotly.graph_objects as go
import requests
import yfinance as yf

_CACHE = {}
_LOCK = Lock()
MARKET_LABELS = {'^KS11':'KOSPI','^KQ11':'KOSDAQ','^GSPC':'S&P 500','^IXIC':'NASDAQ','^VIX':'VIX','KRW=X':'USD/KRW','^TNX':'US 10Y'}
MACRO_LABELS = {'DGS10':'미국 10년물 국채금리','FEDFUNDS':'Fed Funds Rate','CPIAUCSL':'미국 CPI YoY','UNRATE':'미국 실업률'}

def _cached(key, ttl, loader):
    now=time.time()
    with _LOCK:
        hit=_CACHE.get(key)
        if hit and now-hit[0] < ttl:
            return hit[1].copy()
    value=loader()
    with _LOCK: _CACHE[key]=(now,value.copy())
    return value

def market_history(symbol, period='1y'):
    def load():
        frame=yf.download(symbol,period=period,interval='1d',auto_adjust=False,progress=False,threads=False)
        if frame.empty: return pd.DataFrame()
        if isinstance(frame.columns,pd.MultiIndex): frame.columns=frame.columns.get_level_values(0)
        frame=frame.reset_index()
        return pd.DataFrame({'date':pd.to_datetime(frame['Date']),'value':pd.to_numeric(frame['Close'],errors='coerce')}).dropna()
    return _cached(('market',symbol,period),300,load)

def _fred_frame(series_id):
    r=requests.get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}',timeout=10)
    r.raise_for_status()
    frame=pd.read_csv(StringIO(r.text))
    dc,vc=frame.columns[0],frame.columns[-1]
    result=pd.DataFrame({'date':pd.to_datetime(frame[dc],errors='coerce'),'value':pd.to_numeric(frame[vc],errors='coerce')}).dropna()
    if series_id=='CPIAUCSL': result['value']=result['value'].pct_change(12)*100
    return result.dropna()

def macro_history(series_id, years=10):
    def load():
        frame=_fred_frame(series_id)
        cutoff=pd.Timestamp.now()-pd.DateOffset(years=years)
        return frame[frame['date']>=cutoff]
    return _cached(('macro',series_id,years),1800,load)

def make_indicator_figure(kind, code, range_key='1Y'):
    range_map={'1M':('3mo',1),'3M':('6mo',1),'1Y':('1y',1),'5Y':('5y',5),'10Y':('10y',10)}
    if kind=='market':
        period,_=range_map.get(range_key,('1y',1)); frame=market_history(code,period); title=MARKET_LABELS.get(code,code)
    else:
        _,years=range_map.get(range_key,('1y',1)); frame=macro_history(code,years); title=MACRO_LABELS.get(code,code)
    if frame.empty: raise RuntimeError('표시할 지표 데이터가 없습니다.')
    fig=go.Figure(go.Scatter(x=frame['date'],y=frame['value'],mode='lines',name=title,line={'width':2}))
    fig.update_layout(template='plotly_dark',paper_bgcolor='#0f141c',plot_bgcolor='#0f141c',height=520,margin={'l':40,'r':22,'t':55,'b':40},title={'text':f'{title} · {range_key}','x':0.02},hovermode='x unified',showlegend=False)
    fig.update_xaxes(showgrid=False); fig.update_yaxes(gridcolor='rgba(148,163,184,.12)',zeroline=False)
    return title,fig
