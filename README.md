# My Market v0.4 Dashboard

## v0.4 improvements

1. Search autocomplete
   - Search runs while typing.
   - 350ms trailing throttle.
   - Enter still works.

2. Watchlist mini charts
   - 30 latest daily closes.
   - Lightweight SVG sparkline.
   - Cached 10 minutes.

3. Market / macro / news
   - KOSPI, KOSDAQ, S&P 500, NASDAQ, VIX, USD/KRW, US 10Y.
   - FRED: US 10Y, Fed Funds, CPI YoY, unemployment.
   - Watchlist-related Yahoo Finance news.
   - Market cache: 60 seconds.
   - Macro cache: 15 minutes.
   - News cache: 5 minutes.

4. Clock
   - KST and New York time.
   - Updates once per second.

5. Stock detail navigation
   - Sticky "관심종목으로 돌아가기" button.
   - Home button.
   - Bottom back button.

6. 500 timeout fix
   - Detail page shell is rendered first.
   - Remote calls begin after `ui.context.client.connected()`.
   - response_timeout=15 is an additional safety margin.
   - 1D/W/M charts load only when selected.

## GitHub

Upload/replace:

```text
main.py
dashboard_data.py
chart_data.py
kis.py
market_data.py
supabase_store.py
requirements.txt
render.yaml
.gitignore
```

No DB schema change is required from v0.3.

Never upload `.env`.

## Render

No new environment variable is required for v0.4.

Keep:

```text
APP_URL
KIS_APP_KEY
KIS_APP_SECRET
KIS_ENV
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
STORAGE_SECRET
ENABLE_GOOGLE
ENABLE_KAKAO
ENABLE_NAVER
ENABLE_APPLE
REFRESH_SECONDS
```

## Data notes

- Korean current price/full chart: KIS.
- Mini card sparkline and US stock market data: Yahoo Finance via yfinance.
- US macro indicators: FRED public CSV downloads.
- News: Yahoo Finance via yfinance.

These public/free sources are suitable for a personal dashboard prototype but
are not a licensed redistribution feed. If the service is opened widely,
review data redistribution/licensing before treating it as a commercial market-data service.
