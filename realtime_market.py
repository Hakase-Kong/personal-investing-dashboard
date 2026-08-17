import asyncio
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import websockets


class USRealtimeHub:
    """Small shared KIS overseas-stock realtime hub for a single NiceGUI process.

    It keeps one websocket task and a shared in-memory snapshot cache. New symbols
    are added to the subscription set and the socket is restarted so all active
    subscriptions are registered on one session. This is intentionally small and
    suitable for a personal dashboard; use an external streaming service/Redis
    if you later scale to multiple Render workers.
    """

    def __init__(self, app_key: str, app_secret: str, env: str = 'real'):
        self.app_key = app_key
        self.app_secret = app_secret
        self.env = env
        self.subscriptions = {}  # symbol -> exchange
        self.snapshots = {}
        self._task = None
        self._lock = asyncio.Lock()
        self._generation = 0

    @property
    def enabled(self):
        return bool(self.app_key and self.app_secret and self.env != 'demo')

    @property
    def rest_base(self):
        return 'https://openapi.koreainvestment.com:9443'

    @property
    def ws_url(self):
        return 'ws://ops.koreainvestment.com:21000'

    def _approval_key(self):
        response = requests.post(
            f'{self.rest_base}/oauth2/Approval',
            headers={'content-type': 'application/json'},
            json={
                'grant_type': 'client_credentials',
                'appkey': self.app_key,
                'secretkey': self.app_secret,
            },
            timeout=10,
        )
        response.raise_for_status()
        key = response.json().get('approval_key')
        if not key:
            raise RuntimeError('KIS WebSocket approval_key 발급 실패')
        return key

    @staticmethod
    def _prefix(exchange: str):
        e = (exchange or '').upper()
        if 'NAS' in e or e in {'NMS', 'NGM', 'NCM'}:
            return 'DNAS'
        if 'AMEX' in e or e in {'ASE', 'AMX'}:
            return 'DAMS'
        # NYSE, ARCA/PCX ETFs: use the NYSE family key as a practical fallback.
        return 'DNYS'

    @staticmethod
    def _session_now():
        now = datetime.now(ZoneInfo('America/New_York'))
        hm = (now.hour, now.minute)
        if now.weekday() >= 5:
            return 'CLOSED'
        if (4, 0) <= hm < (9, 30):
            return 'PRE'
        if (9, 30) <= hm < (16, 0):
            return 'REGULAR'
        if (16, 0) <= hm < (20, 0):
            return 'POST'
        return 'CLOSED'

    async def subscribe(self, symbol: str, exchange: str):
        if not self.enabled:
            return
        symbol = symbol.upper().strip()
        async with self._lock:
            if self.subscriptions.get(symbol) == exchange and self._task and not self._task.done():
                return
            # Keep a conservative subscription count for this personal server.
            if symbol not in self.subscriptions and len(self.subscriptions) >= 20:
                oldest = next(iter(self.subscriptions))
                self.subscriptions.pop(oldest, None)
            self.subscriptions[symbol] = exchange
            self._generation += 1
            generation = self._generation
            if self._task and not self._task.done():
                self._task.cancel()
            self._task = asyncio.create_task(self._run(generation))

    def seed_extended(self, symbol: str, data: dict):
        symbol = symbol.upper()
        snap = self.snapshots.setdefault(symbol, {})
        for key in ('premarket', 'regular', 'afterhours'):
            if data.get(key) is not None:
                snap[key] = data[key]
        snap.setdefault('session', data.get('session') or self._session_now())
        snap.setdefault('source', 'POLL')

    def get(self, symbol: str):
        snap = dict(self.snapshots.get(symbol.upper(), {}))
        updated = snap.get('updated_at', 0)
        snap['live'] = bool(updated and time.time() - updated < 12)
        if not snap.get('session'):
            snap['session'] = self._session_now()
        return snap

    async def _run(self, generation: int):
        try:
            approval = await asyncio.to_thread(self._approval_key)
            async with websockets.connect(
                self.ws_url,
                ping_interval=None,
                close_timeout=3,
            ) as ws:
                # snapshot subscriptions for this connection
                current = list(self.subscriptions.items())
                for symbol, exchange in current:
                    tr_key = f'{self._prefix(exchange)}{symbol}'
                    payload = {
                        'header': {
                            'approval_key': approval,
                            'custtype': 'P',
                            'tr_type': '1',
                            'content-type': 'utf-8',
                        },
                        'body': {
                            'input': {
                                'tr_id': 'HDFSCNT0',
                                'tr_key': tr_key,
                            }
                        },
                    }
                    await ws.send(json.dumps(payload, ensure_ascii=False))
                    await asyncio.sleep(0.12)

                while generation == self._generation:
                    data = await ws.recv()
                    if not data:
                        continue
                    if isinstance(data, bytes):
                        data = data.decode('utf-8', errors='ignore')

                    if data.startswith('0|'):
                        parts = data.split('|', 3)
                        if len(parts) < 4 or parts[1] != 'HDFSCNT0':
                            continue
                        try:
                            count = int(parts[2])
                        except Exception:
                            count = 1
                        fields = parts[3].split('^')
                        width = 26
                        for i in range(max(1, count)):
                            row = fields[i * width:(i + 1) * width]
                            if len(row) < 15:
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
                            session = self._session_now()
                            snap = self.snapshots.setdefault(symbol, {})
                            snap.update({
                                'last': price,
                                'change': change,
                                'percent': pct,
                                'updated_at': time.time(),
                                'source': 'KIS WS',
                                'session': session,
                                'local_date': row[4] if len(row) > 4 else '',
                                'local_time': row[5] if len(row) > 5 else '',
                            })
                            if session == 'PRE':
                                snap['premarket'] = price
                            elif session == 'REGULAR':
                                snap['regular'] = price
                            elif session == 'POST':
                                snap['afterhours'] = price

                    elif data.startswith('{'):
                        try:
                            message = json.loads(data)
                            if message.get('header', {}).get('tr_id') == 'PINGPONG':
                                await ws.pong(data.encode())
                        except Exception:
                            pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Store the error for diagnostics; UI will keep polling fallback data.
            for symbol in self.subscriptions:
                self.snapshots.setdefault(symbol, {})['ws_error'] = str(exc)[:160]
