import os
from datetime import datetime

from dotenv import load_dotenv
from nicegui import app, ui

from kis import KISClient
from market_data import search_stocks, get_us_quote
from storage import load_watchlist, add_watchlist, remove_watchlist

load_dotenv()

KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_ENV = os.getenv("KIS_ENV", "real")
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "5"))
PORT = int(os.getenv("PORT", "8080"))

kis = KISClient(
    app_key=KIS_APP_KEY,
    app_secret=KIS_APP_SECRET,
    env=KIS_ENV,
)

quote_labels: dict[str, dict] = {}


def fmt_price(value, currency):
    if value is None:
        return "-"
    if currency == "KRW":
        return f"{value:,.0f}원"
    return f"${value:,.2f}"


def fmt_change(change, percent, currency):
    if change is None or percent is None:
        return "-"
    prefix = "+" if change > 0 else ""
    if currency == "KRW":
        return f"{prefix}{change:,.0f}원 ({prefix}{percent:.2f}%)"
    return f"{prefix}${change:,.2f} ({prefix}{percent:.2f}%)"


async def fetch_quote(item):
    if item["market"] == "KR":
        return kis.get_domestic_quote(item["symbol"])
    return get_us_quote(item["symbol"])


async def refresh_quotes():
    watchlist = load_watchlist()
    for item in watchlist:
        key = f"{item['market']}:{item['symbol']}"
        refs = quote_labels.get(key)
        if not refs:
            continue

        try:
            quote = await fetch_quote(item)
            currency = quote.get("currency", "KRW")

            refs["price"].set_text(fmt_price(quote.get("price"), currency))
            refs["change"].set_text(
                fmt_change(
                    quote.get("change"),
                    quote.get("change_percent"),
                    currency,
                )
            )
            refs["time"].set_text(datetime.now().strftime("%H:%M:%S"))

            percent = quote.get("change_percent")
            if percent is not None:
                refs["change"].classes(
                    remove="text-red-400 text-blue-400 text-slate-400"
                )
                if percent > 0:
                    refs["change"].classes(add="text-red-400")
                elif percent < 0:
                    refs["change"].classes(add="text-blue-400")
                else:
                    refs["change"].classes(add="text-slate-400")

        except Exception as exc:
            refs["price"].set_text("조회 실패")
            refs["change"].set_text(str(exc)[:100])
            refs["change"].classes(
                remove="text-red-400 text-blue-400 text-slate-400",
                add="text-slate-400",
            )


def render_watchlist(container):
    container.clear()
    quote_labels.clear()

    watchlist = load_watchlist()

    with container:
        if not watchlist:
            with ui.card().classes("w-full glass-card p-8"):
                ui.label("관심종목이 없습니다.").classes(
                    "text-xl font-semibold text-white"
                )
                ui.label("위 검색창에서 종목을 추가해보세요.").classes(
                    "text-slate-400"
                )
            return

        with ui.grid(columns=3).classes("w-full gap-4 max-lg:grid-cols-2 max-md:grid-cols-1"):
            for item in watchlist:
                key = f"{item['market']}:{item['symbol']}"

                with ui.card().classes("glass-card stock-card p-5"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(item["name"]).classes(
                                "text-lg font-bold text-white"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']}"
                            ).classes("text-xs text-slate-500")

                        ui.label(item["market"]).classes(
                            "market-pill text-xs font-bold"
                        )

                    price = ui.label("불러오는 중...").classes(
                        "text-3xl font-black tracking-tight mt-6 text-white"
                    )

                    change = ui.label("-").classes(
                        "text-sm font-bold text-slate-400 mt-1"
                    )

                    with ui.row().classes(
                        "w-full items-center justify-between mt-6 pt-4 border-t border-slate-800"
                    ):
                        ui.label("마지막 조회").classes(
                            "text-xs text-slate-500"
                        )
                        last_time = ui.label("-").classes(
                            "text-xs text-slate-400"
                        )

                    ui.button(
                        "삭제",
                        on_click=lambda _, m=item["market"], s=item["symbol"]:
                            delete_item(m, s, container),
                    ).props("flat dense").classes(
                        "w-full mt-3 text-slate-500 hover:text-white"
                    )

                    quote_labels[key] = {
                        "price": price,
                        "change": change,
                        "time": last_time,
                    }

        ui.timer(0.1, refresh_quotes, once=True)


def delete_item(market, symbol, container):
    remove_watchlist(market, symbol)
    ui.notify("관심종목에서 삭제했습니다.", type="positive")
    render_watchlist(container)


def add_item(item, container):
    add_watchlist(item)
    ui.notify(f"{item['name']} 추가", type="positive")
    render_watchlist(container)


async def do_search(query, results_container, watchlist_container):
    results_container.clear()

    q = query.value.strip()
    if not q:
        return

    with results_container:
        try:
            results = search_stocks(q)
        except Exception as exc:
            ui.label(f"검색 오류: {exc}").classes("text-red-400")
            return

        if not results:
            ui.label("검색 결과가 없습니다.").classes("text-slate-400")
            return

        with ui.column().classes("w-full gap-2"):
            for i, item in enumerate(results[:10]):
                with ui.card().classes(
                    "w-full glass-card px-4 py-3"
                ):
                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        with ui.column().classes("gap-0"):
                            ui.label(item["name"]).classes(
                                "font-bold text-white"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']} · {item['market']}"
                            ).classes("text-xs text-slate-500")

                        ui.button(
                            "추가",
                            icon="add",
                            on_click=lambda _, x=item:
                                add_item(x, watchlist_container),
                        ).props("unelevated").classes("add-button")


@ui.page("/")
def index():
    ui.add_head_html(
        """
        <style>
            body {
                background:
                    radial-gradient(circle at top left, rgba(26, 42, 70, .35), transparent 32%),
                    #07090d;
                color: #f8fafc;
            }
            .nicegui-content {
                max-width: 1220px;
                margin: 0 auto;
                padding: 30px 24px 70px 24px;
            }
            .glass-card {
                background: rgba(15, 20, 28, .88) !important;
                border: 1px solid rgba(71, 85, 105, .35) !important;
                border-radius: 18px !important;
                box-shadow: none !important;
            }
            .stock-card {
                min-height: 250px;
            }
            .market-pill {
                background: #171d27;
                color: #94a3b8;
                border: 1px solid #273244;
                padding: 5px 8px;
                border-radius: 8px;
            }
            .search-box .q-field__control {
                background: #0e131b !important;
                border-radius: 14px !important;
                min-height: 54px;
            }
            .add-button {
                background: #2563eb !important;
                border-radius: 10px !important;
            }
            .live-dot {
                width: 8px;
                height: 8px;
                border-radius: 999px;
                background: #4ade80;
                box-shadow: 0 0 14px rgba(74, 222, 128, .65);
            }
        </style>
        """
    )

    with ui.row().classes("w-full items-center justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("PERSONAL INVESTMENT TERMINAL").classes(
                "text-[11px] tracking-[.18em] font-bold text-slate-500"
            )
            ui.label("MY MARKET").classes(
                "text-4xl font-black tracking-tight text-white"
            )

        with ui.row().classes(
            "items-center gap-2 px-3 py-2 rounded-full border border-slate-800 bg-slate-900"
        ):
            ui.html('<div class="live-dot"></div>')
            ui.label("ONLINE").classes("text-xs font-bold text-slate-200")

    with ui.grid(columns=3).classes(
        "w-full gap-3 mt-8 max-md:grid-cols-1"
    ):
        with ui.card().classes("glass-card p-5"):
            ui.label("KIS").classes("text-xs font-bold text-slate-500")
            ui.label(
                "CONNECTED" if kis.enabled() else "NOT CONFIGURED"
            ).classes("text-2xl font-bold text-white mt-2")
            ui.label(
                "한국주식 실제 시세"
                if kis.enabled()
                else ".env에 KIS 키를 입력하세요"
            ).classes("text-xs text-slate-500")

        with ui.card().classes("glass-card p-5"):
            ui.label("REFRESH").classes("text-xs font-bold text-slate-500")
            ui.label(f"{REFRESH_SECONDS} sec").classes(
                "text-2xl font-bold text-white mt-2"
            )
            ui.label("가격 자동 갱신").classes("text-xs text-slate-500")

        with ui.card().classes("glass-card p-5"):
            ui.label("WATCHLIST").classes("text-xs font-bold text-slate-500")
            watch_count = ui.label(str(len(load_watchlist()))).classes(
                "text-2xl font-bold text-white mt-2"
            )
            ui.label("저장된 관심종목").classes("text-xs text-slate-500")

    ui.label("종목 검색").classes(
        "text-lg font-bold text-white mt-10 mb-2"
    )

    search_input = ui.input(
        placeholder="삼성전자, 005930, NVDA, NVIDIA, AAPL"
    ).props("outlined dark clearable").classes("w-full search-box")

    results_container = ui.column().classes("w-full mt-2")

    ui.label("관심종목").classes(
        "text-lg font-bold text-white mt-10 mb-2"
    )
    watchlist_container = ui.column().classes("w-full")

    async def search_action():
        await do_search(
            search_input,
            results_container,
            watchlist_container,
        )

    search_input.on("keydown.enter", search_action)
    search_input.on(
        "update:model-value",
        lambda _: ui.timer(0.35, search_action, once=True),
    )

    render_watchlist(watchlist_container)

    async def refresh_all():
        watch_count.set_text(str(len(load_watchlist())))
        await refresh_quotes()

    ui.timer(REFRESH_SECONDS, refresh_all)


@app.get("/health")
def health():
    return {
        "ok": True,
        "kis": kis.enabled(),
        "watchlist": len(load_watchlist()),
        "time": datetime.now().isoformat(),
    }


ui.run(
    host="0.0.0.0",
    port=PORT,
    title="My Market",
    favicon="📈",
    dark=True,
    show=False,
    reload=False,
)
