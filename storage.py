import json
import os
from pathlib import Path

FILE = Path(os.getenv("WATCHLIST_FILE", "watchlist.json"))


def load_watchlist():
    if not FILE.exists():
        return []
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_watchlist(items):
    FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_watchlist(item):
    items = load_watchlist()
    key = (item["market"], item["symbol"])
    if not any((x["market"], x["symbol"]) == key for x in items):
        items.append(item)
        save_watchlist(items)


def remove_watchlist(market, symbol):
    items = [
        x for x in load_watchlist()
        if not (x["market"] == market and x["symbol"] == symbol)
    ]
    save_watchlist(items)
