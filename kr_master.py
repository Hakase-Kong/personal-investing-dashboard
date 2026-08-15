import io
import time
import zipfile
from threading import Lock
import requests

_CACHE = {'loaded_at': 0.0, 'rows': []}
_LOCK = Lock()
SOURCES = [
    ('KOSPI', 'https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip', 'kospi_code.mst', 228),
    ('KOSDAQ', 'https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip', 'kosdaq_code.mst', 222),
]

def _download_market(exchange, url, filename, trailer_len):
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        raw = zf.read(filename).decode('cp949', errors='ignore')
    rows = []
    for line in raw.splitlines():
        if len(line) <= trailer_len + 21:
            continue
        first = line[:-trailer_len]
        short_code = first[0:9].strip()
        standard_code = first[9:21].strip()
        name = first[21:].strip()
        symbol = short_code[-6:] if len(short_code) >= 6 else short_code
        if symbol and name:
            rows.append({'symbol': symbol, 'name': name, 'market': 'KR', 'exchange': exchange, 'standard_code': standard_code})
    return rows

def load_master(force=False):
    now = time.time()
    with _LOCK:
        if not force and _CACHE['rows'] and now - _CACHE['loaded_at'] < 86400:
            return _CACHE['rows']
    rows, errors = [], []
    for exchange, url, filename, trailer_len in SOURCES:
        try:
            rows.extend(_download_market(exchange, url, filename, trailer_len))
        except Exception as exc:
            errors.append(f'{exchange}: {exc}')
    if not rows:
        raise RuntimeError('KIS 국내 종목 마스터를 불러오지 못했습니다. ' + ' / '.join(errors))
    unique = {(r['exchange'], r['symbol']): r for r in rows}
    rows = list(unique.values())
    with _LOCK:
        _CACHE['loaded_at'] = now
        _CACHE['rows'] = rows
    return rows

def search_master(query, limit=20):
    q = (query or '').strip()
    if not q:
        return []
    ql = q.lower()
    try:
        rows = load_master()
    except Exception:
        return []
    matched = []
    for item in rows:
        symbol, name = item['symbol'].lower(), item['name'].lower()
        if ql not in symbol and ql not in name:
            continue
        if symbol == ql: score = 0
        elif name == ql: score = 1
        elif symbol.startswith(ql): score = 2
        elif name.startswith(ql): score = 3
        else: score = 4
        matched.append((score, len(item['name']), item))
    matched.sort(key=lambda x: (x[0], x[1], x[2]['name']))
    return [x[2] for x in matched[:limit]]
