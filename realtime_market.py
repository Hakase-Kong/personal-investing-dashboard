import asyncio
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import websockets


class USRealtimeHub:
    """Shared KIS overseas-stock realtime hub for one NiceGUI process.

    - One websocket for all active US symbols.
    - `subscribe_many` batches subscription changes so the socket is restarted once.
    - Automatic reconnect with exponential backoff.
    - Per-symbol snapshots keep PRE / REGULAR / POST values separately.

    KIS HDFSCNT0 payload layout follows the official sample:
    RSYM, SYMB, ZDIV, TYMD, XYMD, XHMS, KYMD, KHMS, OPEN, HIGH, LOW,
    LAST, SIGN, DIFF, RATE, PBID, PASK, VBID, VASK, EVOL, TVOL, TAMT,
    BIVL, ASVL, STRN, MTYP.
    """

    def __init__(self, app_key: str, app_secret: str, env: str = "real"):
        self.app_key = app_key
        self.app_secret = app_secret
        self.env = env
        self.subscriptions = {}  # symbol -> exchange
        self.snapshots = {}
        self._task = None
        self._lock = asyncio.Lock()
        self._generation = 0
        self._last_socket_error = ""

    @property
    def enabled(self):
        return bool(self.app_key and self.app_secret and self.env != "demo")

    @property
    def rest_base(self):
        return "https://openapi.koreainvestment.com:9443"

    @property
    def ws_url(self):
        return "ws://ops.koreainvestment.com:21000"

    def _approval_key(self):
        response = requests.post(
            f"{self.rest_base}/oauth2/Approval",
            headers={"content-type": "application/json"},
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "secretkey": self.app_secret,
            },
            timeout=10,
        )
        response.raise_for_status()
        key = response.json().get("approval_key")
        if not key:
            raise RuntimeError("KIS WebSocket approval_key 발급 실패")
        return key

    @staticmethod
    def _prefix(exchange: str):
        e = (exchange or "").upper()
        if "NAS" in e or e in {"NMS", "NGM", "NCM"}:
            return "DNAS"
        if "AMEX" in e or e in {"ASE", "AMX", "AMS"}:
            return "DAMS"
        # NYSE / ARCA / PCX are routed through the NYS family for the free feed.
        return "DNYS"

    @staticmethod
    def session_now():
        now = datetime.now(ZoneInfo("America/New_York"))
        hm = (now.hour, now.minute)
        if now.weekday() >= 5:
            return "CLOSED"
        if (4, 0) <= hm < (9, 30):
            return "PRE"
        if (9, 30) <= hm < (16, 0):
            return "REGULAR"
        if (16, 0) <= hm < (20, 0):
            return "POST"
        return "CLOSED"

    async def subscribe(self, symbol: str, exchange: str):
        await self.subscribe_many([(symbol, exchange)])

    async def subscribe_many(self, items):
        """Add many symbols and restart the socket only once if the set changed."""
        if not self.enabled:
            return

        changed = False
        async with self._lock:
            for symbol, exchange in items:
                symbol = str(symbol or "").upper().strip()
                if not symbol:
                    continue
                exchange = str(exchange or "")
                if self.subscriptions.get(symbol) != exchange:
                    self.subscriptions[symbol] = exchange
                    changed = True

            # Conservative limit: keep at most 30 stock trade subscriptions.
            while len(self.subscriptions) > 30:
                oldest = next(iter(self.subscriptions))
                self.subscriptions.pop(oldest, None)
                changed = True

            if not changed and self._task and not self._task.done():
                return

            self._generation += 1
            generation = self._generation
            if self._task and not self._task.done():
                self._task.cancel()
            self._task = asyncio.create_task(self._supervise(generation))

    def seed_extended(self, symbol: str, data: dict):
        symbol = symbol.upper()
        snap = self.snapshots.setdefault(symbol, {})
        for key in ("premarket", "regular", "afterhours"):
            if data.get(key) is not None:
                snap[key] = data[key]
        if data.get("session"):
            snap["session"] = data["session"]
        snap.setdefault("source", "POLL")

    def get(self, symbol: str):
        snap = dict(self.snapshots.get(symbol.upper(), {}))
        updated = snap.get("updated_at", 0)
        snap["live"] = bool(updated and time.time() - updated < 15)
        if not snap.get("session"):
            snap["session"] = self.session_now()
        if self._last_socket_error and not snap.get("ws_error"):
            snap["ws_error"] = self._last_socket_error
        return snap

    async def _supervise(self, generation: int):
        backoff = 1.0
        while generation == self._generation:
            try:
                await self._run_once(generation)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_socket_error = str(exc)[:180]
                for symbol in self.subscriptions:
                    self.snapshots.setdefault(symbol, {})["ws_error"] = self._last_socket_error
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 20.0)

    async def _run_once(self, generation: int):
        approval = await asyncio.to_thread(self._approval_key)
        async with websockets.connect(
            self.ws_url,
            ping_interval=None,
            close_timeout=3,
            open_timeout=8,
        ) as ws:
            current = list(self.subscriptions.items())
            for symbol, exchange in current:
                tr_key = f"{self._prefix(exchange)}{symbol}"
                payload = {
                    "header": {
                        "approval_key": approval,
                        "custtype": "P",
                        "tr_type": "1",
                        "content-type": "utf-8",
                    },
                    "body": {
                        "input": {
                            "tr_id": "HDFSCNT0",
                            "tr_key": tr_key,
                        }
                    },
                }
                await ws.send(json.dumps(payload, ensure_ascii=False))
                await asyncio.sleep(0.12)

            while generation == self._generation:
                data = await asyncio.wait_for(ws.recv(), timeout=45)
                if not data:
                    continue
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="ignore")

                if data.startswith("0|"):
                    parts = data.split("|", 3)
                    if len(parts) < 4 or parts[1] != "HDFSCNT0":
                        continue
                    try:
                        count = int(parts[2])
                    except Exception:
                        count = 1

                    fields = parts[3].split("^")
                    width = 26
                    for i in range(max(1, count)):
                        row = fields[i * width : (i + 1) * width]
                        if len(row) < width:
                            continue
                        symbol = row[1].upper()
                        try:
                            price = float(row[11])
                        except Exception:
                            continue
                        try:
                            change = float(row[13])
                        except Exception:
                            change = None
                        try:
                            pct = float(row[14])
                        except Exception:
                            pct = None

                        session = self.session_now()
                        snap = self.snapshots.setdefault(symbol, {})
                        snap.update(
                            {
                                "last": price,
                                "change": change,
                                "percent": pct,
                                "updated_at": time.time(),
                                "source": "KIS WS",
                                "session": session,
                                "local_date": row[4],
                                "local_time": row[5],
                                "volume": row[20],
                            }
                        )
                        if session == "PRE":
                            snap["premarket"] = price
                        elif session == "REGULAR":
                            snap["regular"] = price
                        elif session == "POST":
                            snap["afterhours"] = price

                elif data.startswith("{"):
                    try:
                        message = json.loads(data)
                        tr_id = message.get("header", {}).get("tr_id")
                        if tr_id == "PINGPONG":
                            await ws.pong(data.encode())
                            continue
                        body = message.get("body", {})
                        if str(body.get("rt_cd", "0")) != "0":
                            msg = body.get("msg1") or "KIS websocket subscription error"
                            if msg != "ALREADY IN SUBSCRIBE":
                                self._last_socket_error = str(msg)[:180]
                    except Exception:
                        pass
