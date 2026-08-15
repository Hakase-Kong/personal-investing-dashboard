import math
import time
from dataclasses import dataclass
from threading import Lock

import numpy as np
import pandas as pd
import yfinance as yf

_CACHE = {}
_LOCK = Lock()


@dataclass
class Metrics:
    cagr: float
    volatility: float
    max_drawdown: float
    sharpe: float


def _cached(key, ttl, loader):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1].copy()
    value = loader()
    with _LOCK:
        _CACHE[key] = (now, value.copy())
    return value


def yf_symbol(item):
    if item["market"] == "KR":
        suffix = ".KQ" if "KOSDAQ" in str(item.get("exchange", "")).upper() else ".KS"
        return f"{item['symbol']}{suffix}"
    return item["symbol"]


def price_history(items, period="5y"):
    symbols = [yf_symbol(item) for item in items]
    key = ("history", tuple(symbols), period)

    def load():
        frame = yf.download(
            symbols,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="column",
        )
        if frame.empty:
            return pd.DataFrame()

        result = pd.DataFrame(index=frame.index)
        if isinstance(frame.columns, pd.MultiIndex):
            for symbol in symbols:
                if ("Close", symbol) in frame.columns:
                    result[symbol] = pd.to_numeric(frame[("Close", symbol)], errors="coerce")
                elif (symbol, "Close") in frame.columns:
                    result[symbol] = pd.to_numeric(frame[(symbol, "Close")], errors="coerce")
        else:
            result[symbols[0]] = pd.to_numeric(frame["Close"], errors="coerce")

        return result.dropna(how="all").ffill().dropna()

    return _cached(key, 1800, load)


def normalize_weights(weights):
    total = sum(max(float(v), 0) for v in weights.values())
    if total <= 0:
        return {k: 0 for k in weights}
    return {k: max(float(v), 0) / total for k, v in weights.items()}


def drift_analysis(positions, target_rows, current_values):
    targets = {
        (r["market"], r["exchange"], r["symbol"]): float(r.get("target_weight") or 0) / 100
        for r in target_rows
    }
    total = sum(current_values.values())
    rows = []

    for position in positions:
        key = (position["market"], position["exchange"], position["symbol"])
        value = float(current_values.get(key, 0))
        current_weight = value / total if total else 0
        target_weight = targets.get(key, 0)
        drift = current_weight - target_weight
        rows.append({
            "key": key,
            "symbol": position["symbol"],
            "name": position["name"],
            "current_weight": current_weight,
            "target_weight": target_weight,
            "drift": drift,
            "value": value,
            "target_value": total * target_weight,
            "trade_amount": total * target_weight - value,
        })

    score = min(100.0, sum(abs(r["drift"]) for r in rows) * 500)
    return rows, score


def contribution_rebalance(drift_rows, contribution):
    contribution = max(float(contribution or 0), 0)
    needs = {
        r["symbol"]: max(r["target_value"] - r["value"], 0)
        for r in drift_rows
    }
    total_need = sum(needs.values())
    if contribution <= 0 or total_need <= 0:
        return []

    result = []
    remaining = contribution
    ordered = sorted(drift_rows, key=lambda r: r["drift"])
    for row in ordered:
        need = needs[row["symbol"]]
        if need <= 0:
            continue
        if total_need <= contribution:
            amount = need
        else:
            amount = contribution * need / total_need
        amount = min(amount, remaining)
        remaining -= amount
        result.append({**row, "contribution_amount": amount})

    if remaining > 1 and result:
        result[0]["contribution_amount"] += remaining
    return result


def _metrics(equity):
    if equity is None or len(equity) < 20:
        return Metrics(0, 0, 0, 0)
    equity = pd.Series(equity).dropna()
    returns = equity.pct_change().dropna()
    years = max(len(returns) / 252, 1 / 252)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if equity.iloc[0] > 0 else 0
    vol = returns.std() * math.sqrt(252) if len(returns) else 0
    drawdown = equity / equity.cummax() - 1
    mdd = drawdown.min() if len(drawdown) else 0
    sharpe = (returns.mean() * 252 / vol) if vol > 0 else 0
    return Metrics(float(cagr), float(vol), float(mdd), float(sharpe))


def _rebalance_dates(index, strategy):
    if strategy == "monthly":
        periods = index.to_period("M")
    elif strategy == "quarterly":
        periods = index.to_period("Q")
    elif strategy == "yearly":
        periods = index.to_period("Y")
    else:
        return set()

    result = set()
    previous = None
    for date, period in zip(index, periods):
        if previous is None or period != previous:
            result.add(date)
            previous = period
    return result


def run_backtest(items, weights_by_symbol, strategy="quarterly", threshold=0.05, period="5y"):
    history = price_history(items, period)
    if history.empty:
        return {"equity": [], "dates": [], "metrics": Metrics(0, 0, 0, 0)}

    mapping = {item["symbol"]: yf_symbol(item) for item in items}
    weights = normalize_weights({mapping[s]: w for s, w in weights_by_symbol.items() if s in mapping})
    columns = [c for c in history.columns if c in weights]
    history = history[columns].dropna()
    weights = {c: weights[c] for c in columns}
    weights = normalize_weights(weights)
    if history.empty or not weights:
        return {"equity": [], "dates": [], "metrics": Metrics(0, 0, 0, 0)}

    returns = history.pct_change().fillna(0)
    shares_value = {c: weights[c] for c in columns}
    portfolio = 1.0
    equity = []
    rebalance_dates = _rebalance_dates(history.index, strategy)

    for i, date in enumerate(history.index):
        if i > 0:
            for c in columns:
                shares_value[c] *= 1 + float(returns.loc[date, c])
            portfolio = sum(shares_value.values())

        total = sum(shares_value.values()) or 1.0
        current_weights = {c: shares_value[c] / total for c in columns}
        should_rebalance = date in rebalance_dates
        if strategy == "threshold":
            should_rebalance = any(abs(current_weights[c] - weights[c]) >= threshold for c in columns)
        elif strategy == "none":
            should_rebalance = False

        if should_rebalance:
            shares_value = {c: portfolio * weights[c] for c in columns}

        equity.append(sum(shares_value.values()))

    metrics = _metrics(equity)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in history.index],
        "equity": [round(float(x), 6) for x in equity],
        "metrics": metrics,
    }


def compare_rebalance_strategies(items, weights_by_symbol, period="5y"):
    configs = [
        ("none", "리밸런싱 없음"),
        ("monthly", "매월"),
        ("quarterly", "분기"),
        ("yearly", "연 1회"),
        ("threshold", "±5%p"),
    ]
    result = []
    for strategy, label in configs:
        test = run_backtest(items, weights_by_symbol, strategy=strategy, threshold=0.05, period=period)
        result.append({"strategy": strategy, "label": label, **test})
    return result


def xray(items, weights_by_symbol, period="2y"):
    weights = normalize_weights(weights_by_symbol)
    top_weight = max(weights.values()) if weights else 0
    hhi = sum(w * w for w in weights.values())
    effective_n = 1 / hhi if hhi > 0 else 0

    region = {"KR": 0.0, "US": 0.0}
    for item in items:
        region[item["market"]] = region.get(item["market"], 0) + weights.get(item["symbol"], 0)

    history = price_history(items, period)
    avg_corr = 0.0
    corr = pd.DataFrame()
    if not history.empty and history.shape[1] >= 2:
        corr = history.pct_change().dropna().corr()
        values = []
        for i in range(len(corr.columns)):
            for j in range(i + 1, len(corr.columns)):
                values.append(float(corr.iloc[i, j]))
        avg_corr = float(np.mean(values)) if values else 0.0

    concentration_score = max(0, min(100, 100 - top_weight * 100 - hhi * 40))
    diversification_score = max(0, min(100, 35 + effective_n * 8 - max(avg_corr, 0) * 25))
    score = round((concentration_score + diversification_score) / 2)

    return {
        "score": score,
        "top_weight": top_weight,
        "effective_n": effective_n,
        "avg_corr": avg_corr,
        "region": region,
        "corr": corr,
    }


def what_if(items, base_weights, symbol, new_weight, period="2y"):
    base = normalize_weights(base_weights)
    if symbol not in base:
        return None
    new_weight = min(max(float(new_weight), 0), 1)
    others = {k: v for k, v in base.items() if k != symbol}
    other_sum = sum(others.values())
    adjusted = {symbol: new_weight}
    for key, value in others.items():
        adjusted[key] = (1 - new_weight) * value / other_sum if other_sum > 0 else 0

    base_test = run_backtest(items, base, strategy="none", period=period)
    new_test = run_backtest(items, adjusted, strategy="none", period=period)
    return {
        "base": base_test["metrics"],
        "new": new_test["metrics"],
        "weights": adjusted,
    }


def stress_tests(items, weights_by_symbol):
    weights = normalize_weights(weights_by_symbol)
    kr = sum(weights.get(i["symbol"], 0) for i in items if i["market"] == "KR")
    us = sum(weights.get(i["symbol"], 0) for i in items if i["market"] == "US")
    scenarios = [
        ("NASDAQ -20%", -(us * 0.20 + kr * 0.06)),
        ("한국주식 -20%", -(kr * 0.20 + us * 0.04)),
        ("글로벌 Risk-off", -(kr * 0.16 + us * 0.18)),
        ("USD/KRW -10%", -(us * 0.10)),
    ]
    return [{"name": name, "shock": shock} for name, shock in scenarios]


def drift_timeline(items, weights_by_symbol, period="2y"):
    history = price_history(items, period)
    if history.empty:
        return {"dates": [], "drift": []}

    mapping = {item["symbol"]: yf_symbol(item) for item in items}
    targets = normalize_weights({
        mapping[symbol]: weight
        for symbol, weight in weights_by_symbol.items()
        if symbol in mapping
    })
    columns = [c for c in history.columns if c in targets]
    history = history[columns].dropna()
    if history.empty:
        return {"dates": [], "drift": []}

    targets = normalize_weights({c: targets[c] for c in columns})
    start_prices = history.iloc[0]
    # Start at exact target allocation with portfolio value 1.0.
    shares = {
        c: targets[c] / float(start_prices[c])
        for c in columns
        if float(start_prices[c]) > 0
    }

    dates = []
    drift_values = []
    for date, row in history.iterrows():
        values = {c: shares[c] * float(row[c]) for c in shares}
        total = sum(values.values()) or 1.0
        current = {c: values[c] / total for c in values}
        # Half-L1 distance: 0% means perfectly on target, 100% is theoretical max.
        drift = 0.5 * sum(abs(current[c] - targets[c]) for c in current)
        dates.append(date.strftime("%Y-%m-%d"))
        drift_values.append(round(drift * 100, 3))

    return {"dates": dates, "drift": drift_values}
