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


## v0.6.1 UI patch

- Increased inactive filter text contrast in dark mode.
- Fixed active filter class switching.
- Removed card skeleton placeholders that could remain as tall empty rectangles.
- Loading placeholders now use compact spinners only.
- Representative stocks increased from 6 to 12.
- Wide-screen representative layout changed to 4 columns.
- Expanded the representative universes so the 12-card view has enough candidates.

Performance impact of 12 cards is modest because quote history for the representative
universe is still fetched in a single batch request per market/mode and cached.

## v0.7 — Search + KIS Ranking + Indicator Charts + Portfolio

### Full Korean stock search
- Downloads official KIS KOSPI/KOSDAQ master files.
- Full ticker/name autocomplete is cached in memory for 24 hours.
- Public home warms the master index in the background after initial render.

### Official Korean rankings
- Market cap ranking: KIS `/uapi/domestic-stock/v1/ranking/market-cap`
- Volume ranking: KIS `/uapi/domestic-stock/v1/quotations/volume-rank`
- Public Korea cards prefer KIS and fall back to the prototype universe if the API is unavailable.

### Indicator detail charts
Click public market/macro cards.

```text
/indicator/market/^GSPC
/indicator/market/KRW=X
/indicator/macro/CPIAUCSL
/indicator/macro/FEDFUNDS
```

Ranges: 1M / 3M / 1Y / 5Y / 10Y.

### Portfolio
Run this once in Supabase SQL Editor:

```text
supabase/schema_v0.7.sql
```

Then the personal dashboard supports:
- quantity
- average purchase price
- current valuation
- P/L
- return
- approximate combined KRW valuation using USD/KRW

No new Render environment variable is required.
