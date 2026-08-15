import time
from dataclasses import dataclass
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
import requests

@dataclass
class Token:
    value:str
    expires_at:float

class KISClient:
    def __init__(self,app_key,app_secret,env="real"):
        self.app_key=app_key;self.app_secret=app_secret;self.env=env;self._token=None
    @property
    def base_url(self):
        return "https://openapivts.koreainvestment.com:29443" if self.env=="demo" else "https://openapi.koreainvestment.com:9443"
    def enabled(self):return bool(self.app_key and self.app_secret)
    def _access_token(self):
        if not self.enabled():raise RuntimeError("KIS API 키가 설정되지 않았습니다.")
        now=time.time()
        if self._token and self._token.expires_at>now+60:return self._token.value
        r=requests.post(f"{self.base_url}/oauth2/tokenP",headers={"content-type":"application/json"},
            json={"grant_type":"client_credentials","appkey":self.app_key,"appsecret":self.app_secret},timeout=10)
        r.raise_for_status();d=r.json();token=d.get("access_token")
        if not token:raise RuntimeError(f"KIS 토큰 발급 실패: {d}")
        self._token=Token(token,now+int(d.get("expires_in",3600)));return token
    def _headers(self,tr_id):
        return {"authorization":f"Bearer {self._access_token()}","appkey":self.app_key,
            "appsecret":self.app_secret,"tr_id":tr_id,"custtype":"P","content-type":"application/json; charset=utf-8"}
    def get_domestic_quote(self,symbol):
        r=requests.get(f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._headers("FHKST01010100"),
            params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":symbol},timeout=10)
        r.raise_for_status();b=r.json()
        if str(b.get("rt_cd"))!="0":raise RuntimeError(b.get("msg1") or "KIS 현재가 조회 실패")
        o=b.get("output") or {};p=_n(o.get("stck_prpr"));ch=_n(o.get("prdy_vrss"));pct=_n(o.get("prdy_ctrt"))
        if str(o.get("prdy_vrss_sign","")) in {"4","5"}:
            if ch is not None:ch=-abs(ch)
            if pct is not None:pct=-abs(pct)
        return {"price":p,"change":ch,"change_percent":pct,"currency":"KRW"}
    def get_domestic_period_chart(self,symbol,period="D",pages=2):
        rows=[];end=date.today()
        for _ in range(max(1,pages)):
            r=requests.get(f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                headers=self._headers("FHKST03010100"),
                params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":symbol,
                "FID_INPUT_DATE_1":"20000101","FID_INPUT_DATE_2":end.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE":period,"FID_ORG_ADJ_PRC":"0"},timeout=10)
            r.raise_for_status();b=r.json()
            if str(b.get("rt_cd"))!="0":raise RuntimeError(b.get("msg1") or "KIS 기간차트 조회 실패")
            batch=b.get("output2") or []
            if not batch:break
            rows.extend(batch);dates=[x.get("stck_bsop_date") for x in batch if x.get("stck_bsop_date")]
            if not dates:break
            end=datetime.strptime(min(dates),"%Y%m%d").date()-timedelta(days=1);time.sleep(.08)
        return rows
    def get_domestic_intraday_chart(self,symbol,chunks=13):
        now=datetime.now(ZoneInfo("Asia/Seoul"))
        cursor="153000" if now.hour<9 or now.hour>15 or (now.hour==15 and now.minute>=30) else now.strftime("%H%M%S")
        rows=[]
        for _ in range(max(1,chunks)):
            r=requests.get(f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                headers=self._headers("FHKST03010200"),
                params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":symbol,
                "FID_INPUT_HOUR_1":cursor,"FID_PW_DATA_INCU_YN":"Y","FID_ETC_CLS_CODE":""},timeout=10)
            r.raise_for_status();b=r.json()
            if str(b.get("rt_cd"))!="0":raise RuntimeError(b.get("msg1") or "KIS 분봉 조회 실패")
            batch=b.get("output2") or []
            if not batch:break
            rows.extend(batch);times=[x.get("stck_cntg_hour") for x in batch if x.get("stck_cntg_hour")]
            if not times:break
            cursor=(datetime.strptime(min(times),"%H%M%S")-timedelta(minutes=1)).strftime("%H%M%S")
            if cursor<"090000":break
            time.sleep(.08)
        return rows

def _n(v):
    try:return None if v in (None,"") else float(v)
    except Exception:return None
