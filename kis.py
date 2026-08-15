import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests


@dataclass
class Token:
    value: str
    expires_at: float


class KISClient:
    def __init__(self, app_key: str, app_secret: str, env: str = "real"):
        self.app_key = app_key
        self.app_secret = app_secret
        self.env = env
        self._token: Token | None = None

    @property
    def base_url(self):
        if self.env == "demo":
            return "https://openapivts.koreainvestment.com:29443"
        return "https://openapi.koreainvestment.com:9443"

    def enabled(self):
        return bool(self.app_key and self.app_secret)

    def _access_token(self):
        if not self.enabled():
            raise RuntimeError("KIS API 키가 설정되지 않았습니다.")

        now = time.time()
        if self._token and self._token.expires_at > now + 60:
            return self._token.value

        response = requests.post(
            f"{self.base_url}/oauth2/tokenP",
            headers={"content-type": "application/json"},
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError(f"KIS 토큰 발급 실패: {data}")

        expires_in = int(data.get("expires_in", 3600))
        self._token = Token(
            value=access_token,
            expires_at=now + expires_in,
        )
        return access_token

    def _headers(self, tr_id: str):
        return {
            "authorization": f"Bearer {self._access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "content-type": "application/json; charset=utf-8",
        }

    def get_domestic_quote(self, symbol: str):
        response = requests.get(
            f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._headers("FHKST01010100"),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
            },
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()

        if str(body.get("rt_cd")) != "0":
            raise RuntimeError(body.get("msg1") or "KIS 현재가 조회 실패")

        output = body.get("output") or {}

        price = _num(output.get("stck_prpr"))
        change = _num(output.get("prdy_vrss"))
        percent = _num(output.get("prdy_ctrt"))
        sign = str(output.get("prdy_vrss_sign", ""))

        if sign in {"4", "5"}:
            if change is not None:
                change = -abs(change)
            if percent is not None:
                percent = -abs(percent)

        return {
            "price": price,
            "change": change,
            "change_percent": percent,
            "currency": "KRW",
        }

    def get_domestic_period_chart(
        self,
        symbol: str,
        period: str = "D",
        pages: int = 2,
    ) -> list[dict]:
        """D/W/M chart. KIS returns at most 100 rows per request."""
        rows = []
        current_end = date.today()

        for _ in range(max(1, pages)):
            response = requests.get(
                f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                headers=self._headers("FHKST03010100"),
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                    "FID_INPUT_DATE_1": "20000101",
                    "FID_INPUT_DATE_2": current_end.strftime("%Y%m%d"),
                    "FID_PERIOD_DIV_CODE": period,
                    "FID_ORG_ADJ_PRC": "0",
                },
                timeout=10,
            )
            response.raise_for_status()
            body = response.json()

            if str(body.get("rt_cd")) != "0":
                raise RuntimeError(
                    body.get("msg1") or "KIS 기간차트 조회 실패"
                )

            batch = body.get("output2") or []
            if not batch:
                break

            rows.extend(batch)

            dates = [
                x.get("stck_bsop_date")
                for x in batch
                if x.get("stck_bsop_date")
            ]
            if not dates:
                break

            earliest = min(dates)
            try:
                earliest_date = datetime.strptime(
                    earliest,
                    "%Y%m%d",
                ).date()
            except ValueError:
                break

            current_end = earliest_date - timedelta(days=1)
            time.sleep(0.08)

        return rows

    def get_domestic_intraday_chart(
        self,
        symbol: str,
        chunks: int = 13,
    ) -> list[dict]:
        """Fetch enough 1-minute chunks to cover most/all of a KRX session.

        KIS provides max 30 records per call for this endpoint.
        Responses are cached at the chart_data layer.
        """
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        if now.hour < 9:
            cursor = "153000"
        elif now.hour > 15 or (now.hour == 15 and now.minute >= 30):
            cursor = "153000"
        else:
            cursor = now.strftime("%H%M%S")

        rows = []

        for _ in range(max(1, chunks)):
            response = requests.get(
                f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                headers=self._headers("FHKST03010200"),
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                    "FID_INPUT_HOUR_1": cursor,
                    "FID_PW_DATA_INCU_YN": "Y",
                    "FID_ETC_CLS_CODE": "",
                },
                timeout=10,
            )
            response.raise_for_status()
            body = response.json()

            if str(body.get("rt_cd")) != "0":
                raise RuntimeError(
                    body.get("msg1") or "KIS 분봉 조회 실패"
                )

            batch = body.get("output2") or []
            if not batch:
                break

            rows.extend(batch)

            times = [
                x.get("stck_cntg_hour")
                for x in batch
                if x.get("stck_cntg_hour")
            ]
            if not times:
                break

            earliest = min(times)
            try:
                t = datetime.strptime(earliest, "%H%M%S")
                t -= timedelta(minutes=1)
                cursor = t.strftime("%H%M%S")
            except ValueError:
                break

            if cursor < "090000":
                break

            time.sleep(0.08)

        return rows


def _num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
