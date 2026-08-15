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
