# My Market v0.5 — Public Home + Personal Dashboard

## Route structure

```text
/             Public market dashboard (no login required)
/login        Login
/signup       Email signup
/dashboard    Personal dashboard (login required)
/stock/...    Public stock detail/chart
```

## Public home

- KOSPI / KOSDAQ / S&P 500 / NASDAQ / VIX / USD-KRW / US10Y
- Korea / US representative stock tabs
- "시가총액 대표" tab
- "거래 활발" tab
- Recent daily sparkline on representative stocks
- FRED macro indicators
- Market news
- Login / personal-dashboard CTA

### Important ranking note

This zero-cost prototype does **not** claim to screen every listed stock in real time.

- `시가총액 대표`: curated large-cap universe, ordered as representative large caps.
- `거래 활발`: dynamically sorted by latest volume inside that representative universe.

This avoids dozens/hundreds of KIS/Yahoo calls on every anonymous page view.
A later version can replace this with KIS ranking APIs and the official KRX/KIS master universe.

## Personal dashboard

- Supabase Auth
- User-specific watchlist
- Type-ahead search
- Current price
- 30-day mini chart
- Watchlist news
- Macro indicators

## Stock detail

No login required:
- Current price
- 1D / daily / weekly / monthly chart
- MA5 / MA20 / MA60 / MA120
- Previous-page button
- Market-home button

If logged in:
- Add stock to personal watchlist
- Personal-dashboard button

## GitHub files

Upload/replace:

```text
main.py
public_data.py
dashboard_data.py
chart_data.py
kis.py
market_data.py
supabase_store.py
requirements.txt
render.yaml
.gitignore
```

No Supabase schema change is required from v0.3/v0.4.

## Render

No new environment variable is required.

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

## Notes

The public dashboard uses free/unofficial Yahoo Finance data for several market
views and representative-stock calculations. This is appropriate for a personal
prototype, but redistribution/licensing should be reviewed before opening the
service broadly or using it commercially.

NiceGUI pages build a visible shell before expensive remote requests whenever
possible, then wait for the client connection before performing asynchronous
API work.
