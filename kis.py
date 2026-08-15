import time
from dataclasses import dataclass

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


def _num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
