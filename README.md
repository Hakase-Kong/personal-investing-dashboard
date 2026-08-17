# My Market v0.8 — Portfolio Lab + ECharts

## Core direction

v0.8 differentiates My Market from a brokerage trading UI by focusing on **portfolio decision support**:

- public market dashboard
- personal watchlist and portfolio
- fast ECharts stock/indicator charts
- target allocation and drift
- exact rebalance buy/sell amounts
- cash-only / no-sell rebalance suggestions
- rebalance backtesting
- drift timeline
- Portfolio X-Ray
- What-if simulator
- Stress Test
- in-app rebalance threshold alerts
- portfolio allocation donut

## Important UX fixes

### No more card-click collision
Watchlist cards are not clickable as a whole.

Each card has explicit buttons:

```text
[상세차트] [포트폴리오]
```

This prevents `포트폴리오` from bubbling into stock-detail navigation.

### Personal dashboard no longer loses public-market context
The logged-in dashboard includes:

- total portfolio value / cost / P&L
- market index mini charts
- watchlist mini charts
- portfolio allocation
- macro indicators
- personal news
- Portfolio Lab

## Plotly removed

`plotly` is no longer a dependency.

Stock detail and indicator detail use NiceGUI's native `ui.echart` wrapper around Apache ECharts.

Stock detail includes:

- candlestick
- volume
- MA5 / MA20 / MA60 / MA120
- 1D / daily / weekly / monthly
- inside zoom + slider
- cached historical data

The default page loads daily candles only. Intraday / weekly / monthly data are loaded only when selected.

## Portfolio Lab

### Target allocation / drift
Store a target weight for each position and see:

- current weight
- target weight
- drift in percentage points
- KRW buy/sell amount required to restore target

### Smart Rebalance
Enter a new cash contribution and My Market allocates it toward underweight positions without selling overweight positions.

### Rebalance alert
Store a drift threshold such as `±5%p`.

When any position exceeds the threshold the dashboard shows an in-app rebalance alert.

This release does not send email/Telegram/push alerts yet.

### Backtest
Compares the same target allocation under:

- no rebalance
- monthly
- quarterly
- annual
- ±5 percentage-point threshold

Outputs:

- CAGR
- Max Drawdown
- Sharpe
- normalized equity curve

### Drift Timeline
Shows how far the portfolio would have drifted from its target weights over the last two years without rebalancing.

### Portfolio X-Ray
Initial X-Ray includes:

- Portfolio Score
- top-position concentration
- effective number of holdings
- average historical correlation
- KR / US regional allocation

### What-if
Change one asset's target weight. Remaining assets are rescaled proportionally. The tool compares historical:

- volatility
- max drawdown
- Sharpe

### Stress Test
Initial deterministic scenarios:

- NASDAQ -20%
- Korean equities -20%
- global risk-off
- USD/KRW -10%

These are scenario calculations, not forecasts.

## Backtest caveats

Historical simulation is for analysis only. It currently does **not** model:

- brokerage fees
- taxes
- bid/ask spread
- slippage
- dividends not captured by adjusted-price source behavior
- actual trade execution constraints

Historical results are not predictions.

## Supabase migrations

If v0.7 portfolio migration has already been run, run only:

```text
supabase/schema_v0.8.sql
```

If starting from v0.6 or earlier, run:

```text
supabase/schema_v0.7.sql
supabase/schema_v0.8.sql
```

v0.8 adds:

```text
target_allocations
rebalance_rules
```

Both use RLS so authenticated users can access only their own rows.

## GitHub files

Replace/add:

```text
main.py
chart_data.py
indicator_data.py
portfolio_lab.py
public_data.py
dashboard_data.py
market_data.py
kr_master.py
kis.py
supabase_store.py
requirements.txt
render.yaml
.gitignore
supabase/schema_v0.7.sql
supabase/schema_v0.8.sql
```

Do not upload `.env` or `__pycache__`.

## Render

No new Render environment variable is required compared with v0.7.

## Data architecture / performance

- current KR quote: KIS
- KR historical chart: KIS first, Yahoo fallback
- US chart/history: Yahoo Finance prototype source
- macro: FRED
- index history: Yahoo Finance prototype source
- KR stock master: official KIS master ZIP
- server-memory chart cache:
  - current/intraday: short TTL
  - daily: ~10 min
  - weekly: ~30 min
  - monthly: ~1 hour
- Portfolio Lab historical data: cached ~30 min

For a commercial/public redistribution service, review data licensing and redistribution terms before scaling beyond personal/prototype use.


## v0.9 — Tabs / currency / card alignment / NAVER News

### Personal dashboard tabs
- Overview
- Portfolio
- Portfolio Lab
- Market
- News

### Watchlist card layout
Cards use a fixed internal grid:
- fixed two-line name area
- market badge fixed at the top-right
- fixed price/change area
- fixed sparkline area
- actions pinned to the bottom
- delete moved into the `...` menu

This keeps Korean and long US names vertically aligned.

### Portfolio input and valuation safety
- quantity must be > 0
- average price must be > 0
- KR stocks explicitly use KRW / ₩
- US stocks explicitly use USD / $
- a failed current-price fetch is no longer treated as zero
- unpriced positions are excluded from total valuation/P&L instead of showing a false -100% loss

### Base currency
Portfolio summary and allocation can use:
- KRW
- USD

USD positions are converted with the current USD/KRW snapshot. The selected base currency is stored in Supabase `user_preferences`.

Run once:
```text
supabase/schema_v0.9.sql
```

### NAVER News
Add these Render environment variables:
```text
NAVER_CLIENT_ID
NAVER_CLIENT_SECRET
```

The News tab supports:
- Integrated
- NAVER
- Yahoo

NAVER results and Yahoo results are de-duplicated by normalized title.

## v1.0 Global Markets / Chart Hotfix

### Chart fix
NiceGUI's EChart `options` property is mutable but is not assigned with a setter.
This release replaces `chart.options = options` with:

```python
chart.options.clear()
chart.options.update(options)
chart.update()
```

This fixes the runtime error `property 'options' of 'EChart' object has no setter`.

### US extended-hours
US stock detail pages show three snapshots when available:
- pre-market
- regular session
- after-hours

The prototype uses Yahoo intraday `prepost=True` data for these session snapshots.
The main regular quote remains the existing quote source.

### Futures
A separate Futures view now includes:
- S&P 500 E-mini
- NASDAQ 100 E-mini
- Dow futures
- Russell 2000 futures
- WTI crude
- Gold
- Silver
- Copper

### FX
The Market Center now includes:
- USD/KRW
- JPY/KRW
- EUR/KRW
- CNY/KRW
- USD/JPY
- EUR/USD
- GBP/USD

### Bonds
US Treasury curve is built from FRED daily constant-maturity series:
1M, 3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y.

Korean government bond curve is loaded from Bank of Korea ECOS table `817Y002`
by discovering the current item codes dynamically. Add `ECOS_API_KEY` to Render for
reliable use. The code falls back to the public `sample` key if no key is set, but
that key is heavily rate-limited.

### Render environment variable
Optional but strongly recommended:

```text
ECOS_API_KEY
```

No Supabase migration is required for v1.0.


## v1.1 Market Intelligence

### Heatmap
Public and personal Market Center now include a `히트맵` tab.
- US: large-cap representative universe, tile area uses a stable representative weight and color uses daily return.
- Korea: KIS market-cap ranking is used; tile area is rank-derived to avoid per-stock extra calls.

### Live US extended hours
`realtime_market.py` adds a shared in-process KIS WebSocket hub using `HDFSCNT0`.
- PRE / REGULAR / POST session cards update from the shared cache every 1 second.
- Yahoo extended-hours polling remains a fallback/seed every 15 seconds.
- `KIS LIVE` appears when a WebSocket trade was received recently.
- One process keeps up to 20 detailed-stock subscriptions conservatively.

Add dependency: `websockets` (already included in requirements.txt).
No new environment variable is required; it reuses `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ENV`.

### Bond intelligence
Bond panels now include clickable maturities.
Routes:
- `/bond/us/2Y`, `/bond/us/5Y`, `/bond/us/10Y`, `/bond/us/30Y`
- `/bond/kr/3Y`, `/bond/kr/5Y`, `/bond/kr/10Y`, etc.
- `/bond/spread/10Y-2Y`

Each route provides 1Y / 3Y / 5Y / 10Y historical line charts.
US data is based on FRED H.15 series. Korea history uses ECOS 817Y002 and works best with `ECOS_API_KEY`.

### Notes
- KIS WebSocket mapping uses DNAS for NASDAQ, DAMS for AMEX and DNYS as the NYSE/ARCA-family fallback, based on KIS sample conventions.
- If WebSocket registration is rejected for a particular exchange code, the UI continues with the polling fallback instead of failing the stock page.
- The heatmap is a market overview visualization, not a complete exchange-wide commercial market-data feed.

## v1.2 Live Cards + Historical Yield Curves

### US representative cards now follow KIS realtime
When the public page is showing US representative stocks, v1.2 subscribes the visible symbols in one batch to the shared `HDFSCNT0` websocket hub.

The card price and change update once per second from the shared cache and display a session badge:

```text
● PRE LIVE
● REG LIVE
● POST LIVE
```

The stock detail headline price is also synchronized to the same live PRE/REG/POST trade cache. The 15-second extended-hours poll remains as a fallback.

### Websocket reliability
`realtime_market.py` now:

- batches subscriptions with `subscribe_many`
- restarts the socket only once when the subscription set changes
- automatically reconnects with exponential backoff
- parses the official 26-field HDFSCNT0 overseas trade payload
- keeps PRE / REGULAR / POST prices separately

A single Render process shares the feed between users. This is still an in-memory design; multiple Render workers would need Redis/pub-sub or another shared realtime layer.

### Korean Treasury fix
The old implementation depended on `StatisticItemList`, which is unreliable with the ECOS `sample` key. v1.2 instead:

1. uses known stable 817Y002 item codes for 1Y / 3Y / 5Y / 10Y / 20Y
2. discovers additional tenors such as 2Y / 30Y from recent `StatisticSearch` observations when available
3. paginates historical ECOS series rather than requesting an oversized single page

For reliable 2Y / 30Y and long-history access, set a real `ECOS_API_KEY` in Render.

### Bonds UI
The Bond tab is now split into:

```text
[ 현재 YC ] [ YC 변화 ] [ 스프레드 ]
```

`현재 YC`
- US and Korea current yield curves
- click any maturity to open its historical chart

`YC 변화`
- current
- 1 month ago
- 3 months ago
- 1 year ago

All four curves are overlaid so curve flattening, steepening and inversion can be compared visually.

`스프레드`
- US 10Y-2Y preview chart directly in the tab
- Korea 10Y-2Y preview when Korean 2Y is available
- detail chart buttons

### No Supabase migration
v1.2 does not change the database schema.

### Recommended Render environment variable

```text
ECOS_API_KEY=<your Bank of Korea ECOS API key>
```

The rest of the environment variables are unchanged from v1.1.
