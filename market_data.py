from functools import lru_cache
import yfinance as yf

KR_NAMES=[
("005930","삼성전자","KOSPI"),("005935","삼성전자우","KOSPI"),
("000660","SK하이닉스","KOSPI"),("207940","삼성바이오로직스","KOSPI"),
("006400","삼성SDI","KOSPI"),("009150","삼성전기","KOSPI"),
("032830","삼성생명","KOSPI"),("000810","삼성화재","KOSPI"),
("028260","삼성물산","KOSPI"),("010140","삼성중공업","KOSPI"),
("018260","삼성에스디에스","KOSPI"),("373220","LG에너지솔루션","KOSPI"),
("005380","현대차","KOSPI"),("000270","기아","KOSPI"),
("068270","셀트리온","KOSPI"),("035420","NAVER","KOSPI"),
("035720","카카오","KOSPI"),("105560","KB금융","KOSPI"),
("055550","신한지주","KOSPI"),("051910","LG화학","KOSPI"),
("012450","한화에어로스페이스","KOSPI"),("086790","하나금융지주","KOSPI"),
("316140","우리금융지주","KOSPI"),("247540","에코프로비엠","KOSDAQ"),
]

def search_stocks(query):
    q=query.strip();ql=q.lower();out=[]
    for symbol,name,exchange in KR_NAMES:
        if ql in symbol.lower() or ql in name.lower():
            out.append({"symbol":symbol,"name":name,"market":"KR","exchange":exchange})
    if q.isdigit() and len(q)==6 and not any(x["symbol"]==q for x in out):
        out.insert(0,{"symbol":q,"name":q,"market":"KR","exchange":"KR"})
    try:
        s=yf.Search(q,max_results=10,news_count=0)
        for x in getattr(s,"quotes",[]) or []:
            if str(x.get("quoteType","")).upper() not in {"EQUITY","ETF"}:continue
            symbol=str(x.get("symbol","")).strip()
            if not symbol or symbol.endswith(".KS") or symbol.endswith(".KQ"):continue
            out.append({
                "symbol":symbol,
                "name":str(x.get("longname") or x.get("shortname") or x.get("name") or symbol),
                "market":"US",
                "exchange":str(x.get("exchange") or x.get("exchDisp") or "US").upper(),
            })
    except Exception:pass
    def score(x):
        s=x["symbol"].lower();n=x["name"].lower()
        if s==ql:return 0
        if n==ql:return 1
        if s.startswith(ql):return 2
        if n.startswith(ql):return 3
        return 4
    uniq={}
    for x in out:uniq[(x["market"],x["symbol"])]=x
    return sorted(uniq.values(),key=score)[:12]

@lru_cache(maxsize=256)
def ticker(symbol):return yf.Ticker(symbol)

def get_us_quote(symbol):
    t=ticker(symbol);i=t.fast_info
    p=_f(getattr(i,"last_price",None));prev=_f(getattr(i,"previous_close",None))
    if p is None:
        h=t.history(period="5d",interval="1d")
        if h.empty:raise RuntimeError(f"{symbol} 가격 조회 실패")
        p=float(h["Close"].iloc[-1]);prev=float(h["Close"].iloc[-2]) if len(h)>1 else p
    ch=p-prev if prev not in (None,0) else None
    pct=ch/prev*100 if ch is not None and prev else None
    return {"price":p,"change":ch,"change_percent":pct,"currency":"USD"}

def _f(v):
    try:return None if v is None else float(v)
    except Exception:return None
