import time
from threading import Lock

import pandas as pd
import yfinance as yf

_CACHE = {}
_LOCK = Lock()

US_HEATMAP = [
    ('NVDA','NVIDIA','Semiconductor',18), ('MSFT','Microsoft','Technology',17),
    ('AAPL','Apple','Technology',16), ('AMZN','Amazon','Consumer',12),
    ('GOOGL','Alphabet','Communication',11), ('META','Meta','Communication',10),
    ('AVGO','Broadcom','Semiconductor',9), ('TSLA','Tesla','Consumer',8),
    ('BRK-B','Berkshire','Financial',8), ('JPM','JPMorgan','Financial',7),
    ('WMT','Walmart','Consumer',6), ('LLY','Eli Lilly','Healthcare',6),
    ('V','Visa','Financial',6), ('MA','Mastercard','Financial',5),
    ('NFLX','Netflix','Communication',5), ('COST','Costco','Consumer',5),
    ('AMD','AMD','Semiconductor',5), ('PLTR','Palantir','Technology',4),
    ('ORCL','Oracle','Technology',4), ('CRM','Salesforce','Technology',4),
    ('XOM','Exxon Mobil','Energy',4), ('UNH','UnitedHealth','Healthcare',4),
    ('KO','Coca-Cola','Consumer',3), ('BAC','Bank of America','Financial',3),
]


def _cached(key, ttl, loader):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = loader()
    with _LOCK:
        _CACHE[key] = (now, value)
    return value


def _color(pct):
    if pct is None:
        return '#334155'
    # Korean market convention used by the rest of the dashboard: red up, blue down.
    strength = min(abs(pct) / 5.0, 1.0)
    if pct >= 0:
        return '#7f1d1d' if strength > .65 else '#b91c1c' if strength > .3 else '#dc2626'
    return '#1e3a8a' if strength > .65 else '#1d4ed8' if strength > .3 else '#2563eb'


def get_us_heatmap():
    def load():
        symbols = [x[0] for x in US_HEATMAP]
        frame = yf.download(
            symbols, period='5d', interval='1d', auto_adjust=False,
            progress=False, threads=True, group_by='column',
        )
        rows = []
        for symbol, name, sector, weight in US_HEATMAP:
            try:
                if isinstance(frame.columns, pd.MultiIndex):
                    closes = pd.to_numeric(frame[('Close', symbol)], errors='coerce').dropna()
                else:
                    closes = pd.to_numeric(frame['Close'], errors='coerce').dropna()
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) > 1 else last
                pct = (last / prev - 1) * 100 if prev else 0.0
            except Exception:
                pct = None
            rows.append({
                'symbol': symbol, 'name': name, 'sector': sector,
                'percent': pct, 'weight': weight, 'color': _color(pct),
            })
        return rows
    return _cached('us-heatmap', 90, load)


def get_kr_heatmap(kis, limit=24):
    def load():
        rows = []
        try:
            ranked = kis.get_market_cap_rank('0000', limit)
        except Exception:
            ranked = []
        for idx, item in enumerate(ranked):
            pct = item.get('percent')
            rows.append({
                'symbol': item.get('symbol'),
                'name': item.get('name') or item.get('symbol'),
                'sector': 'KR Large Cap',
                'percent': pct,
                # rank-derived area: stable without extra per-stock market-cap calls
                'weight': max(limit - idx, 4),
                'color': _color(pct),
            })
        return rows
    return _cached('kr-heatmap', 90, load)


def echart_treemap(rows, title):
    data = []
    for row in rows:
        pct = row.get('percent')
        pct_text = '-' if pct is None else f'{pct:+.2f}%'
        data.append({
            'name': f"{row.get('symbol','')}\n{pct_text}",
            'value': row.get('weight') or 1,
            'itemStyle': {'color': row.get('color') or '#334155'},
            'tooltip_name': row.get('name') or row.get('symbol'),
        })
    return {
        'animation': False,
        'backgroundColor': 'transparent',
        'title': {'text': title, 'left': 8, 'top': 6, 'textStyle': {'color': '#e2e8f0', 'fontSize': 14}},
        'tooltip': {'trigger': 'item'},
        'series': [{
            'type': 'treemap',
            'top': 38, 'left': 4, 'right': 4, 'bottom': 4,
            'roam': False, 'nodeClick': False, 'breadcrumb': {'show': False},
            'label': {'show': True, 'color': '#fff', 'fontWeight': 'bold', 'fontSize': 11},
            'upperLabel': {'show': False},
            'itemStyle': {'borderColor': '#0f172a', 'borderWidth': 2, 'gapWidth': 2},
            'data': data,
        }],
    }
