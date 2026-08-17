import asyncio
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import websockets


class USRealtimeHub:
    """Shared KIS overseas-stock realtime hub.

    Improvements over v1.2:
    - subscription ACK state per symbol
    - official-sample pacing (0.5s between subscriptions)
    - reconnect without losing last-known prices
    - optional batched REST/Yahoo fallback provider
    - explicit LIVE / ACKED / FALLBACK / ERROR state instead of endless 'waiting'
    """

    def __init__(self, app_key: str, app_secret: str, env: str = "real", fallback_provider=None):
        self.app_key = app_key
        self.app_secret = app_secret
        self.env = env
        self.fallback_provider = fallback_provider
        self.subscriptions: dict[str, str] = {}
        self.snapshots: dict[str, dict] = {}
        self.status: dict[str, dict] = {}
        self._task = None
        self._fallback_task = None
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
        if not items:
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
                state = self.status.setdefault(symbol, {})
                state.setdefault("state", "SUBSCRIBING")

            # Keep within a conservative subscription budget.
            while len(self.subscriptions) > 30:
                oldest = next(iter(self.subscriptions))
                self.subscriptions.pop(oldest, None)
                self.status.pop(oldest, None)
                changed = True

            if changed or not self._task or self._task.done():
                self._generation += 1
                generation = self._generation
                if self._task and not self._task.done():
                    self._task.cancel()
                self._task = asyncio.create_task(self._supervise(generation))

            if self.fallback_provider and (not self._fallback_task or self._fallback_task.done()):
                self._fallback_task = asyncio.create_task(self._fallback_loop())

    def seed_extended(self, symbol: str, data: dict):
        symbol = symbol.upper()
        snap = self.snapshots.setdefault(symbol, {})
        for key in ("premarket", "regular", "afterhours"):
            if data.get(key) is not None:
                snap[key] = data[key]
        if data.get("last") is not None:
            snap["fallback_last"] = data["last"]
        if data.get("percent") is not None:
            snap["fallback_percent"] = data["percent"]
        if data.get("change") is not None:
            snap["fallback_change"] = data["change"]
        if data.get("session"):
            snap["session"] = data["session"]
        snap["fallback_at"] = time.time()

    def get(self, symbol: str):
        symbol = symbol.upper()
        snap = dict(self.snapshots.get(symbol, {}))
        state = dict(self.status.get(symbol, {}))
        now = time.time()
        updated = snap.get("updated_at", 0)
        live = bool(updated and now - updated < 12)
        session = snap.get("session") or self.session_now()

        if live:
            source_state = "LIVE"
            value = snap.get("last")
            pct = snap.get("percent")
            change = snap.get("change")
        elif snap.get("fallback_at") and now - snap.get("fallback_at", 0) < 25:
            source_state = "FALLBACK"
            value = snap.get("fallback_last")
            pct = snap.get("fallback_percent")
            change = snap.get("fallback_change")
        elif state.get("acked"):
            source_state = "ACKED"
            value = snap.get("last")
            pct = snap.get("percent")
            change = snap.get("change")
        elif state.get("error"):
            source_state = "ERROR"
            value = snap.get("last")
            pct = snap.get("percent")
            change = snap.get("change")
        else:
            source_state = "SUBSCRIBING"
            value = snap.get("last")
            pct = snap.get("percent")
            change = snap.get("change")

        snap.update(
            {
                "live": live,
                "session": session,
                "state": source_state,
                "display_last": value,
                "display_percent": pct,
                "display_change": change,
                "acked": bool(state.get("acked")),
                "ws_error": state.get("error") or self._last_socket_error,
            }
        )
        return snap

    def diagnostics(self):
        return {
            "subscriptions": len(self.subscriptions),
            "socket_error": self._last_socket_error,
            "symbols": {
                s: {
                    **self.status.get(s, {}),
                    "last_tick_age": (
                        round(time.time() - self.snapshots.get(s, {}).get("updated_at", 0), 1)
                        if self.snapshots.get(s, {}).get("updated_at")
                        else None
                    ),
                }
                for s in self.subscriptions
            },
        }

    async def _fallback_loop(self):
        while True:
            await asyncio.sleep(8)
            symbols = list(self.subscriptions.items())
            if not symbols:
                continue
            stale = []
            now = time.time()
            for symbol, exchange in symbols:
                last_tick = self.snapshots.get(symbol, {}).get("updated_at", 0)
                if not last_tick or now - last_tick > 10:
                    stale.append((symbol, exchange))
            if not stale:
                continue
            try:
                data = await asyncio.to_thread(self.fallback_provider, stale)
                for symbol, payload in (data or {}).items():
                    self.seed_extended(symbol, payload)
            except Exception:
                pass

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
                    self.status.setdefault(symbol, {})["error"] = self._last_socket_error
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
            self._last_socket_error = ""
            current = list(self.subscriptions.items())
            for symbol, exchange in current:
                self.status.setdefault(symbol, {}).update(
                    {"state": "SUBSCRIBING", "error": "", "acked": False}
                )
                tr_key = f"{self._prefix(exchange)}{symbol}"
                payload = {
                    "header": {
                        "approval_key": approval,
                        "custtype": "P",
                        "tr_type": "1",
                        "content-type": "utf-8",
                    },
                    "body": {"input": {"tr_id": "HDFSCNT0", "tr_key": tr_key}},
                }
                await ws.send(json.dumps(payload, ensure_ascii=False))
                # Official KIS websocket sample spaces subscriptions by 0.5 sec.
                await asyncio.sleep(0.5)

            while generation == self._generation:
                try:
                    data = await asyncio.wait_for(ws.recv(), timeout=45)
                except asyncio.TimeoutError:
                    await ws.ping()
                    continue
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
                        self.status.setdefault(symbol, {}).update(
                            {"state": "LIVE", "acked": True, "error": ""}
                        )

                elif data.startswith("{"):
                    try:
                        message = json.loads(data)
                        header = message.get("header", {})
                        tr_id = header.get("tr_id")
                        if tr_id == "PINGPONG":
                            await ws.pong(data.encode())
                            continue
                        body = message.get("body", {})
                        tr_key = str(header.get("tr_key") or "")
                        symbol = next(
                            (s for s in self.subscriptions if tr_key.endswith(s)),
                            None,
                        )
                        rt_cd = str(body.get("rt_cd", "0"))
                        msg = str(body.get("msg1") or "")
                        if symbol:
                            state = self.status.setdefault(symbol, {})
                            if rt_cd == "0" or msg == "ALREADY IN SUBSCRIBE":
                                state.update({"acked": True, "state": "ACKED", "error": ""})
                            else:
                                state.update({"acked": False, "state": "ERROR", "error": msg})
                        if rt_cd != "0" and msg != "ALREADY IN SUBSCRIBE":
                            self._last_socket_error = msg[:180]
                    except Exception:
                        pass
