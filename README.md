# My Market v0.6 — Search, Sparklines, Speed, Theme

## Main improvements

### 1. Public search
The `/` public dashboard now has the same type-ahead stock search as the personal dashboard.

- 280 ms trailing throttle
- stale-result protection
- search result opens public stock chart
- no login required

### 2. Market and macro mini charts
Market cards now receive 30 recent daily values in the same batch request used for the headline value.

- KOSPI
- KOSDAQ
- S&P 500
- NASDAQ
- VIX
- USD/KRW
- US 10Y

Macro cards also contain recent FRED series and can render a sparkline.

### 3. Performance optimizations
The public page now:
- renders shell/skeletons first
- uses one batched Yahoo download for all market indices instead of seven downloads
- uses one batched download per representative stock universe
- loads market / representative stocks / macro / news concurrently with `asyncio.gather`
- caches market data for 120s
- caches representative stocks for 180s
- caches macro for 30 minutes
- caches news for 10 minutes
- protects autocomplete from stale slower responses

The personal dashboard also parallelizes Supabase profile/watchlist and macro loading.

### 4. Cleaner representative-stock filters
Instead of two separate NiceGUI toggle rows, the controls now appear as one compact segmented toolbar:

```text
[ 한국장 ] [ 미국장 ] | [ 시가총액 대표 ] [ 거래 활발 ]
```

Active choices use the app accent color.

### 5. Theme
Default is **System**.

Header contrast icon menu:
- 시스템 설정
- 라이트 모드
- 다크 모드

NiceGUI's `ui.dark_mode(value=None)` follows the browser/OS color preference.
The selected override is saved in `app.storage.user`.

## Files to replace

```text
main.py
dashboard_data.py
public_data.py
market_data.py
supabase_store.py
kis.py
chart_data.py
requirements.txt
render.yaml
.gitignore
```

No Supabase SQL change and no new Render environment variable are required.

## Note

Plotly stock-detail charts remain dark-themed in this release, even if the surrounding page is light. This makes candlesticks consistently legible. A later version can rebuild Plotly figures when the theme changes if full chart-theme synchronization is desired.
