import asyncio
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import websockets


class KRRealtimeHub:
    """Shared Korea-stock realtime hub.

    Feeds:
    - H0STANC0: KRX expected execution (opening/closing auction)
    - H0STCNT0: KRX regular realtime trades
    - H0STOUP0: KRX after-hours single-price realtime trades (16:00~18:00)

    The first six fields of the KRX expected/regular payload share the same
    structure: symbol, time, price, sign, change, percent.  The after-hours
    parser intentionally relies on those common leading fields only so minor
    schema additions do not break the dashboard.
    """

    MAX_SYMBOLS = 12
    POINT_LIMIT = 420
    LIVE_AGE = 10.0

    def __init__(self, app_key: str, app_secret: str, env: str = 'real'):
        self.app_key = app_key
        self.app_secret = app_secret
        self.env = env
        self.subscriptions = {}
        self.snapshots = {}
        self.status = {}
        self._task = None
        self._generation = 0
        self._lock = asyncio.Lock()
        self._last_error = ''

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
        body = response.json()
        key = body.get('approval_key')
        if not key:
            raise RuntimeError(body.get('msg1') or 'KIS 국내 WebSocket approval_key 발급 실패')
        return key

    @staticmethod
    def session_now():
        now = datetime.now(ZoneInfo('Asia/Seoul'))
        if now.weekday() >= 5:
            return 'CLOSED'
        hm = (now.hour, now.minute)
        if (8, 20) <= hm < (9, 0):
            return 'PRE'
        if (9, 0) <= hm < (15, 20):
            return 'REGULAR'
        if (15, 20) <= hm < (15, 30):
            return 'CLOSING'
        if (16, 0) <= hm < (18, 0):
            return 'AFTER'
        return 'CLOSED'

    def _append_point(self, symbol, price, source='', ts=None):
        try:
            price = float(price)
        except Exception:
            return False
        symbol = str(symbol).upper()
        snap = self.snapshots.setdefault(symbol, {})
        points = snap.setdefault('points', [])
        ts = float(ts or time.time())
        if points:
            last_ts, last_price = float(points[-1][0]), float(points[-1][1])
            if abs(last_price - price) < 1e-12 and ts - last_ts < 12:
                return False
        points.append([ts, price])
        if len(points) > self.POINT_LIMIT:
            del points[:-self.POINT_LIMIT]
        snap['tick_seq'] = int(snap.get('tick_seq', 0)) + 1
        snap['point_source'] = source
        return True

    def seed(self, symbol, price=None, pct=None, change=None, spark=None):
        symbol = str(symbol).upper()
        snap = self.snapshots.setdefault(symbol, {})
        if spark and not snap.get('points'):
            now = time.time()
            vals = []
            for i, value in enumerate(spark[-60:]):
                try:
                    vals.append([now - (len(spark[-60:]) - i) * 60, float(value)])
                except Exception:
                    pass
            if vals:
                snap['points'] = vals
                snap['tick_seq'] = int(snap.get('tick_seq', 0)) + 1
        if price is not None:
            try:
                snap['fallback_last'] = float(price)
                self._append_point(symbol, price, 'INITIAL')
            except Exception:
                pass
        if pct is not None:
            try: snap['fallback_percent'] = float(pct)
            except Exception: pass
        if change is not None:
            try: snap['fallback_change'] = float(change)
            except Exception: pass
        snap['fallback_at'] = time.time()
        snap.setdefault('session', self.session_now())

    async def subscribe(self, symbol):
        await self.subscribe_many([symbol])

    async def subscribe_many(self, symbols):
        changed = False
        async with self._lock:
            for symbol in symbols:
                symbol = str(symbol or '').upper().strip()
                if not symbol:
                    continue
                if symbol not in self.subscriptions:
                    self.subscriptions[symbol] = time.time()
                    changed = True
                state = self.status.setdefault(symbol, {})
                state.setdefault('regular_acked', False)
                state.setdefault('expected_acked', False)
                state.setdefault('after_acked', False)
                state['requested_at'] = time.time()

            while len(self.subscriptions) > self.MAX_SYMBOLS:
                oldest = next(iter(self.subscriptions))
                self.subscriptions.pop(oldest, None)
                self.status.pop(oldest, None)
                changed = True

            if self.enabled and (changed or not self._task or self._task.done()):
                self._generation += 1
                gen = self._generation
                if self._task and not self._task.done():
                    self._task.cancel()
                self._task = asyncio.create_task(self._supervise(gen))

    def get(self, symbol):
        symbol = str(symbol).upper()
        snap = dict(self.snapshots.get(symbol, {}))
        state = dict(self.status.get(symbol, {}))
        now = time.time()
        session = self.session_now()

        source_field = {
            'PRE': 'expected_at',
            'CLOSING': 'expected_at',
            'REGULAR': 'regular_at',
            'AFTER': 'after_at',
        }.get(session)
        source_age = now - float(snap.get(source_field) or 0) if source_field else 99999
        live = source_age < self.LIVE_AGE

        if session in ('PRE', 'CLOSING'):
            value = snap.get('expected')
            pct = snap.get('expected_percent')
            change = snap.get('expected_change')
            channel = 'EXPECTED'
            acked = state.get('expected_acked')
        elif session == 'AFTER':
            value = snap.get('after')
            pct = snap.get('after_percent')
            change = snap.get('after_change')
            channel = 'AFTER'
            acked = state.get('after_acked')
        else:
            value = snap.get('regular')
            pct = snap.get('regular_percent')
            change = snap.get('regular_change')
            channel = 'REGULAR'
            acked = state.get('regular_acked')

        if value is None:
            value = snap.get('fallback_last')
        if pct is None:
            pct = snap.get('fallback_percent')
        if change is None:
            change = snap.get('fallback_change')

        if live:
            display_state = 'LIVE'
        elif acked:
            display_state = 'READY'
        elif state.get('error'):
            display_state = 'ERROR'
        else:
            display_state = 'SNAPSHOT'

        snap.update({
            'session': session,
            'channel': channel,
            'state': display_state,
            'live': live,
            'display_last': value,
            'display_percent': pct,
            'display_change': change,
            'live_points': list(snap.get('points') or []),
            'tick_seq': int(snap.get('tick_seq', 0)),
            'ws_error': state.get('error') or self._last_error,
            'regular_acked': bool(state.get('regular_acked')),
            'expected_acked': bool(state.get('expected_acked')),
            'after_acked': bool(state.get('after_acked')),
        })
        return snap

    async def _supervise(self, generation):
        backoff = 1.0
        while generation == self._generation:
            try:
                await self._run_once(generation)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)[:180]
                for symbol in self.subscriptions:
                    self.status.setdefault(symbol, {})['error'] = self._last_error
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)

    async def _register(self, ws, approval, tr_id, symbol):
        payload = {
            'header': {
                'approval_key': approval,
                'custtype': 'P',
                'tr_type': '1',
                'content-type': 'utf-8',
            },
            'body': {'input': {'tr_id': tr_id, 'tr_key': symbol}},
        }
        await ws.send(json.dumps(payload, ensure_ascii=False))

    async def _run_once(self, generation):
        approval = await asyncio.to_thread(self._approval_key)
        async with websockets.connect(
            self.ws_url,
            ping_interval=None,
            close_timeout=3,
            open_timeout=8,
        ) as ws:
            self._last_error = ''
            # 3 feeds x 12 symbols = 36 registrations, leaving headroom below
            # the KIS realtime registration ceiling.
            for symbol in list(self.subscriptions):
                state = self.status.setdefault(symbol, {})
                state.update({'regular_acked': False, 'expected_acked': False, 'after_acked': False, 'error': ''})
                for tr_id in ('H0STCNT0', 'H0STANC0', 'H0STOUP0'):
                    await self._register(ws, approval, tr_id, symbol)
                    await asyncio.sleep(0.15)

            while generation == self._generation:
                try:
                    data = await asyncio.wait_for(ws.recv(), timeout=20)
                except asyncio.TimeoutError:
                    pong = await ws.ping()
                    await asyncio.wait_for(pong, timeout=5)
                    continue

                if isinstance(data, bytes):
                    data = data.decode('utf-8', errors='ignore')
                if not data:
                    continue

                if data.startswith('0|'):
                    parts = data.split('|', 3)
                    if len(parts) < 4:
                        continue
                    tr_id = parts[1]
                    try: count = max(1, int(parts[2]))
                    except Exception: count = 1
                    fields = parts[3].split('^')
                    width = max(6, len(fields) // count)
                    for i in range(count):
                        row = fields[i*width:(i+1)*width]
                        if len(row) < 6:
                            continue
                        symbol = str(row[0] or '').upper()
                        if symbol not in self.subscriptions:
                            continue
                        try: price = float(row[2])
                        except Exception: continue
                        try: change = float(row[4])
                        except Exception: change = None
                        try: pct = float(row[5])
                        except Exception: pct = None
                        snap = self.snapshots.setdefault(symbol, {})
                        now = time.time()
                        if tr_id == 'H0STCNT0':
                            snap.update({'regular': price, 'regular_change': change, 'regular_percent': pct, 'regular_at': now, 'session': 'REGULAR'})
                            self.status.setdefault(symbol, {}).update({'regular_acked': True, 'error': ''})
                            self._append_point(symbol, price, 'H0STCNT0')
                        elif tr_id == 'H0STANC0':
                            snap.update({'expected': price, 'expected_change': change, 'expected_percent': pct, 'expected_at': now})
                            self.status.setdefault(symbol, {}).update({'expected_acked': True, 'error': ''})
                            if self.session_now() in ('PRE', 'CLOSING'):
                                self._append_point(symbol, price, 'H0STANC0')
                        elif tr_id == 'H0STOUP0':
                            snap.update({'after': price, 'after_change': change, 'after_percent': pct, 'after_at': now, 'session': 'AFTER'})
                            self.status.setdefault(symbol, {}).update({'after_acked': True, 'error': ''})
                            if self.session_now() == 'AFTER':
                                self._append_point(symbol, price, 'H0STOUP0')

                elif data.startswith('{'):
                    try:
                        msg = json.loads(data)
                        header = msg.get('header', {})
                        tr_id = str(header.get('tr_id') or '')
                        if tr_id == 'PINGPONG':
                            await ws.pong(data.encode())
                            continue
                        tr_key = str(header.get('tr_key') or '')
                        symbol = tr_key[-6:].upper() if tr_key else ''
                        if symbol not in self.subscriptions:
                            continue
                        body = msg.get('body', {})
                        rt_cd = str(body.get('rt_cd', '0'))
                        text = str(body.get('msg1') or '')
                        ok = rt_cd == '0' or 'ALREADY IN SUBSCRIBE' in text
                        state = self.status.setdefault(symbol, {})
                        if tr_id == 'H0STCNT0': state['regular_acked'] = ok
                        elif tr_id == 'H0STANC0': state['expected_acked'] = ok
                        elif tr_id == 'H0STOUP0': state['after_acked'] = ok
                        if ok:
                            state['error'] = ''
                        else:
                            state['error'] = f'{tr_id}: {text}'[:180]
                    except Exception:
                        pass

    def diagnostics(self):
        return {
            'enabled': self.enabled,
            'subscriptions': len(self.subscriptions),
            'registrations': len(self.subscriptions) * 3,
            'last_error': self._last_error,
            'symbols': {
                symbol: {
                    **self.status.get(symbol, {}),
                    'session': self.session_now(),
                    'points': len(self.snapshots.get(symbol, {}).get('points') or []),
                }
                for symbol in self.subscriptions
            },
        }
