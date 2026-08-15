import asyncio
import json
import os
from datetime import datetime
from urllib.parse import parse_qs, quote
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from nicegui import app, ui

from chart_data import get_chart_figure
from dashboard_data import (
    get_macro_overview,
    get_market_overview,
    get_sparkline_svg,
    get_watchlist_news,
)
from kis import KISClient
from market_data import get_us_quote, search_stocks
from supabase_store import (
    add_watchlist,
    delete_watchlist,
    get_profile,
    get_user,
    load_watchlist,
    sign_in,
    sign_out,
    sign_up,
)

load_dotenv()

KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_ENV = os.getenv("KIS_ENV", "real")
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "5"))
PORT = int(os.getenv("PORT", "8080"))
STORAGE_SECRET = os.getenv("STORAGE_SECRET", "change-this-in-render")
APP_URL = os.getenv("APP_URL", "").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")

ENABLE_GOOGLE = os.getenv("ENABLE_GOOGLE", "true").lower() == "true"
ENABLE_KAKAO = os.getenv("ENABLE_KAKAO", "true").lower() == "true"
ENABLE_NAVER = os.getenv("ENABLE_NAVER", "true").lower() == "true"
ENABLE_APPLE = os.getenv("ENABLE_APPLE", "false").lower() == "true"

kis = KISClient(KIS_APP_KEY, KIS_APP_SECRET, KIS_ENV)


def add_global_style():
    ui.add_head_html(
        """
        <style>
            body {
                background:
                    radial-gradient(circle at top left, rgba(26,42,70,.35), transparent 32%),
                    #07090d;
                color:#f8fafc;
            }
            .nicegui-content {
                max-width:1220px;
                margin:0 auto;
                padding:30px 24px 70px;
            }
            .glass-card {
                background:rgba(15,20,28,.92)!important;
                border:1px solid rgba(71,85,105,.35)!important;
                border-radius:18px!important;
                box-shadow:none!important;
            }
            .stock-card {
                min-height:330px;
                cursor:pointer;
                transition:transform .15s ease,border-color .15s ease;
            }
            .stock-card:hover {
                transform:translateY(-2px);
                border-color:rgba(96,165,250,.6)!important;
            }
            .market-pill {
                background:#171d27;
                color:#94a3b8;
                border:1px solid #273244;
                padding:5px 8px;
                border-radius:8px;
            }
            .search-box .q-field__control,
            .auth-input .q-field__control {
                background:#0e131b!important;
                border-radius:14px!important;
            }
            .primary-button {
                background:#2563eb!important;
                border-radius:10px!important;
            }
            .social-button {
                border:1px solid #334155!important;
                border-radius:12px!important;
                min-height:46px;
                background:#111827!important;
                color:#f8fafc!important;
            }
            .kakao-button { background:#fee500!important; color:#111827!important; border-color:#fee500!important; }
            .naver-button { background:#03c75a!important; color:white!important; border-color:#03c75a!important; }
            .live-dot {
                width:8px;height:8px;border-radius:999px;background:#4ade80;
                box-shadow:0 0 14px rgba(74,222,128,.65);
            }
            .chart-wrap {
                background:rgba(15,20,28,.92);
                border:1px solid rgba(71,85,105,.35);
                border-radius:18px;
                overflow:hidden;
            }
            .news-row {
                border-bottom:1px solid rgba(51,65,85,.6);
            }
            .news-row:last-child { border-bottom:0; }
        </style>
        """
    )


def is_logged_in():
    return bool(
        app.storage.user.get("access_token")
        and app.storage.user.get("refresh_token")
    )


def save_session_tokens(access_token, refresh_token):
    app.storage.user["access_token"] = access_token
    app.storage.user["refresh_token"] = refresh_token


def save_auth_result(result):
    if result.session:
        save_session_tokens(
            result.session.access_token,
            result.session.refresh_token,
        )
    if result.user:
        app.storage.user["user_id"] = str(result.user.id)
        app.storage.user["email"] = result.user.email or ""


def clear_session():
    for key in [
        "access_token", "refresh_token", "user_id",
        "email", "display_name",
    ]:
        app.storage.user.pop(key, None)


def require_login():
    if not is_logged_in():
        ui.navigate.to("/login")
        return False
    return True


def social_auth_url(provider):
    if not SUPABASE_URL or not APP_URL:
        raise RuntimeError("SUPABASE_URL / APP_URL 설정이 필요합니다.")
    redirect_to = f"{APP_URL}/oauth/callback"
    return (
        f"{SUPABASE_URL}/auth/v1/authorize"
        f"?provider={quote(provider, safe=':')}"
        f"&redirect_to={quote(redirect_to, safe='')}"
    )


async def go_social(provider):
    url = social_auth_url(provider)
    await ui.run_javascript(
        f"window.location.assign({json.dumps(url)});"
    )


def social_buttons():
    if ENABLE_GOOGLE:
        ui.button(
            "Google로 계속하기", icon="login",
            on_click=lambda: go_social("google"),
        ).props("unelevated").classes("w-full social-button")
    if ENABLE_KAKAO:
        ui.button(
            "카카오로 계속하기", icon="chat",
            on_click=lambda: go_social("kakao"),
        ).props("unelevated").classes(
            "w-full social-button kakao-button"
        )
    if ENABLE_NAVER:
        ui.button(
            "네이버로 계속하기", icon="account_circle",
            on_click=lambda: go_social("custom:naver"),
        ).props("unelevated").classes(
            "w-full social-button naver-button"
        )
    if ENABLE_APPLE:
        ui.button(
            "Apple로 계속하기", icon="apple",
            on_click=lambda: go_social("apple"),
        ).props("unelevated").classes("w-full social-button")


@ui.page("/login")
def login_page():
    add_global_style()
    if is_logged_in():
        ui.navigate.to("/")
        return

    with ui.column().classes(
        "w-full min-h-[82vh] items-center justify-center"
    ):
        with ui.card().classes("glass-card w-full max-w-md p-8"):
            ui.label("MY MARKET").classes(
                "text-3xl font-black tracking-tight text-white"
            )
            ui.label("나만의 투자 대시보드").classes(
                "text-slate-400 mb-5"
            )
            with ui.column().classes("w-full gap-2"):
                social_buttons()

            with ui.row().classes("w-full items-center gap-3 my-4"):
                ui.separator().classes("flex-1 bg-slate-800")
                ui.label("또는").classes("text-xs text-slate-500")
                ui.separator().classes("flex-1 bg-slate-800")

            email = ui.input("이메일").props(
                "outlined dark"
            ).classes("w-full auth-input")
            password = ui.input(
                "비밀번호", password=True,
                password_toggle_button=True,
            ).props("outlined dark").classes("w-full auth-input")

            async def handle_login():
                try:
                    result = await asyncio.to_thread(
                        sign_in, email.value.strip(), password.value
                    )
                    save_auth_result(result)
                    ui.navigate.to("/")
                except Exception as exc:
                    ui.notify(f"로그인 실패: {exc}", type="negative")

            ui.button(
                "이메일로 로그인", on_click=handle_login
            ).props("unelevated").classes(
                "w-full h-12 primary-button text-base font-bold mt-2"
            )
            ui.link("회원가입", "/signup").classes(
                "w-full text-center text-blue-400 mt-4 no-underline"
            )


@ui.page("/signup")
def signup_page():
    add_global_style()
    if is_logged_in():
        ui.navigate.to("/")
        return

    with ui.column().classes(
        "w-full min-h-[82vh] items-center justify-center"
    ):
        with ui.card().classes("glass-card w-full max-w-md p-8"):
            ui.label("MY MARKET").classes(
                "text-3xl font-black text-white"
            )
            display_name = ui.input("표시 이름").props(
                "outlined dark"
            ).classes("w-full auth-input")
            email = ui.input("이메일").props(
                "outlined dark"
            ).classes("w-full auth-input")
            password = ui.input(
                "비밀번호", password=True,
                password_toggle_button=True,
            ).props("outlined dark").classes("w-full auth-input")
            confirm = ui.input(
                "비밀번호 확인", password=True,
                password_toggle_button=True,
            ).props("outlined dark").classes("w-full auth-input")

            async def handle_signup():
                if password.value != confirm.value:
                    ui.notify("비밀번호가 서로 다릅니다.", type="warning")
                    return
                try:
                    result = await asyncio.to_thread(
                        sign_up,
                        email.value.strip(),
                        password.value,
                        (display_name.value or "").strip(),
                    )
                    if result.session:
                        save_auth_result(result)
                        ui.navigate.to("/")
                    else:
                        ui.notify(
                            "가입되었습니다. 인증 메일을 확인해주세요.",
                            type="positive",
                            timeout=8000,
                        )
                        ui.navigate.to("/login")
                except Exception as exc:
                    ui.notify(f"회원가입 실패: {exc}", type="negative")

            ui.button(
                "회원가입", on_click=handle_signup
            ).props("unelevated").classes(
                "w-full h-12 primary-button mt-2"
            )


@ui.page("/oauth/callback")
def oauth_callback():
    add_global_style()
    with ui.column().classes(
        "w-full min-h-[80vh] items-center justify-center"
    ):
        ui.spinner(size="lg")
        ui.label("로그인을 완료하고 있습니다...").classes(
            "text-slate-300 mt-4"
        )

    async def finalize():
        try:
            hash_value = await ui.run_javascript(
                "window.location.hash || ''"
            )
            params = parse_qs(str(hash_value).lstrip("#"))
            access_token = params.get("access_token", [None])[0]
            refresh_token = params.get("refresh_token", [None])[0]
            if access_token and refresh_token:
                save_session_tokens(access_token, refresh_token)
                ui.navigate.to("/")
                return
            error = params.get(
                "error_description", params.get("error", [None])
            )[0]
            ui.notify(
                f"소셜 로그인 실패: {error or '토큰 없음'}",
                type="negative",
            )
            ui.navigate.to("/login")
        except Exception as exc:
            ui.notify(f"OAuth 처리 실패: {exc}", type="negative")
            ui.navigate.to("/login")

    ui.timer(0.5, finalize, once=True)


def _format_market_value(item):
    value = item.get("value")
    if value is None:
        return "-"
    suffix = item.get("suffix", "")
    if item["symbol"] == "KRW=X":
        return f"{value:,.1f}원"
    if suffix == "%":
        return f"{value:.2f}%"
    return f"{value:,.2f}"


@ui.page("/")
async def dashboard():
    add_global_style()
    if not require_login():
        return

    # Build page shell immediately; remote calls happen after connection.
    header_name = ui.label("MY MARKET").classes("hidden")

    with ui.row().classes("w-full items-start justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("PERSONAL INVESTMENT TERMINAL").classes(
                "text-[11px] tracking-[.18em] font-bold text-slate-500"
            )
            ui.label("MY MARKET").classes(
                "text-4xl font-black tracking-tight text-white"
            )

        with ui.row().classes("items-center gap-4"):
            with ui.column().classes("items-end gap-0"):
                clock_kst = ui.label("--:--:-- KST").classes(
                    "text-lg font-black text-white tabular-nums"
                )
                clock_ny = ui.label("--:-- NY").classes(
                    "text-xs text-slate-500 tabular-nums"
                )
            with ui.row().classes(
                "items-center gap-2 px-3 py-2 rounded-full "
                "border border-slate-800 bg-slate-900"
            ):
                ui.html('<div class="live-dot"></div>')
                ui.label("ONLINE").classes(
                    "text-xs font-bold text-slate-200"
                )
            account_button = ui.button(
                icon="account_circle"
            ).props("flat round color=grey")

    stats_container = ui.grid(columns=3).classes(
        "w-full gap-3 mt-8 max-md:grid-cols-1"
    )
    market_container = ui.column().classes("w-full mt-9")
    search_section = ui.column().classes("w-full mt-9")
    watchlist_section = ui.column().classes("w-full mt-9")
    macro_container = ui.column().classes("w-full mt-10")
    news_container = ui.column().classes("w-full mt-10")

    await ui.context.client.connected()

    def update_clock():
        kst = datetime.now(ZoneInfo("Asia/Seoul"))
        ny = datetime.now(ZoneInfo("America/New_York"))
        clock_kst.set_text(kst.strftime("%H:%M:%S KST"))
        clock_ny.set_text(ny.strftime("%H:%M:%S NY · %a"))

    update_clock()
    ui.timer(1.0, update_clock)

    try:
        user = await asyncio.to_thread(get_user, app.storage.user)
        profile = await asyncio.to_thread(get_profile, app.storage.user)
        watchlist_items = await asyncio.to_thread(
            load_watchlist, app.storage.user
        )
        if not user:
            raise RuntimeError("사용자 확인 실패")
    except Exception:
        clear_session()
        ui.navigate.to("/login")
        return

    display_name = (
        (profile or {}).get("display_name")
        or app.storage.user.get("email")
        or "User"
    )

    async def logout():
        try:
            await asyncio.to_thread(sign_out, app.storage.user)
        except Exception:
            pass
        clear_session()
        ui.navigate.to("/login")

    with account_button:
        with ui.menu():
            ui.label(display_name).classes(
                "font-bold px-4 pt-3 text-slate-800"
            )
            ui.label(app.storage.user.get("email", "")).classes(
                "text-xs px-4 pb-2 text-slate-500"
            )
            ui.separator()
            ui.menu_item("로그아웃", logout)

    with stats_container:
        with ui.card().classes("glass-card p-5"):
            ui.label("ACCOUNT").classes(
                "text-xs font-bold text-slate-500"
            )
            ui.label(display_name).classes(
                "text-xl font-bold text-white mt-2"
            )
            ui.label("Supabase Auth").classes(
                "text-xs text-slate-500"
            )
        with ui.card().classes("glass-card p-5"):
            ui.label("KIS").classes(
                "text-xs font-bold text-slate-500"
            )
            ui.label(
                "CONNECTED" if kis.enabled() else "NOT CONFIGURED"
            ).classes("text-xl font-bold text-white mt-2")
            ui.label("한국주식 시세").classes(
                "text-xs text-slate-500"
            )
        with ui.card().classes("glass-card p-5"):
            ui.label("WATCHLIST").classes(
                "text-xs font-bold text-slate-500"
            )
            watch_count = ui.label(str(len(watchlist_items))).classes(
                "text-xl font-bold text-white mt-2"
            )
            ui.label("내 관심종목").classes(
                "text-xs text-slate-500"
            )

    # MARKET OVERVIEW
    with market_container:
        ui.label("시장 한눈에 보기").classes(
            "text-lg font-bold text-white mb-3"
        )
        market_grid = ui.grid(columns=7).classes(
            "w-full gap-2 max-xl:grid-cols-4 max-md:grid-cols-2"
        )

    async def load_markets():
        data = await asyncio.to_thread(get_market_overview)
        market_grid.clear()
        with market_grid:
            for item in data:
                pct = item.get("percent")
                color = (
                    "text-red-400"
                    if pct is not None and pct > 0
                    else "text-blue-400"
                    if pct is not None and pct < 0
                    else "text-slate-400"
                )
                with ui.card().classes("glass-card px-4 py-3"):
                    ui.label(item["name"]).classes(
                        "text-xs text-slate-500 font-bold"
                    )
                    ui.label(_format_market_value(item)).classes(
                        "text-lg font-black text-white"
                    )
                    ui.label(
                        "-"
                        if pct is None
                        else f"{pct:+.2f}%"
                    ).classes(f"text-xs font-bold {color}")

    await load_markets()
    ui.timer(60, load_markets)

    # SEARCH AUTOCOMPLETE
    with search_section:
        ui.label("종목 검색").classes(
            "text-lg font-bold text-white mb-2"
        )
        search_input = ui.input(
            placeholder="삼성, 삼성전자, 005930, NVDA, NVIDIA, AAPL"
        ).props("outlined dark clearable").classes(
            "w-full search-box"
        )
        results_container = ui.column().classes(
            "w-full mt-2 gap-2"
        )

    async def do_search():
        q = (search_input.value or "").strip()
        results_container.clear()
        if not q:
            return

        try:
            results = await asyncio.to_thread(search_stocks, q)
        except Exception as exc:
            with results_container:
                ui.label(f"검색 오류: {exc}").classes("text-red-400")
            return

        with results_container:
            if not results:
                ui.label("검색 결과가 없습니다.").classes(
                    "text-slate-500 px-2"
                )
                return
            for item in results[:8]:
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
                                f"{item['symbol']} · "
                                f"{item['exchange']} · "
                                f"{item['market']}"
                            ).classes("text-xs text-slate-500")

                        async def add_item(current=item):
                            saved = await asyncio.to_thread(
                                add_watchlist,
                                app.storage.user,
                                current,
                            )
                            exists = any(
                                x["market"] == current["market"]
                                and x["exchange"] == current["exchange"]
                                and x["symbol"] == current["symbol"]
                                for x in watchlist_items
                            )
                            if not exists:
                                watchlist_items.append(saved or current)
                            search_input.set_value("")
                            results_container.clear()
                            await render_watchlist()
                            await load_news()

                        ui.button(
                            "추가", icon="add",
                            on_click=add_item,
                        ).props("unelevated").classes("primary-button")

    # NiceGUI supports throttled/trailing events: automatic recommendations.
    search_input.on(
        "update:model-value",
        lambda _: do_search(),
        throttle=0.35,
        leading_events=False,
        trailing_events=True,
    )
    search_input.on("keydown.enter", lambda _: do_search())

    # WATCHLIST + SPARKLINES
    with watchlist_section:
        ui.label("관심종목").classes(
            "text-lg font-bold text-white mb-3"
        )
        watchlist_container = ui.column().classes("w-full")

    quote_refs = {}

    async def fetch_quote(item):
        if item["market"] == "KR":
            return await asyncio.to_thread(
                kis.get_domestic_quote, item["symbol"]
            )
        return await asyncio.to_thread(
            get_us_quote, item["symbol"]
        )

    async def render_watchlist():
        watchlist_container.clear()
        quote_refs.clear()
        watch_count.set_text(str(len(watchlist_items)))

        with watchlist_container:
            if not watchlist_items:
                with ui.card().classes("w-full glass-card p-8"):
                    ui.label("관심종목이 없습니다.").classes(
                        "text-xl font-semibold text-white"
                    )
                return

            with ui.grid(columns=3).classes(
                "w-full gap-4 max-lg:grid-cols-2 max-md:grid-cols-1"
            ):
                for item in watchlist_items:
                    key = (
                        f"{item['market']}:"
                        f"{item['exchange']}:"
                        f"{item['symbol']}"
                    )

                    with ui.card().classes(
                        "glass-card stock-card p-5"
                    ) as card:
                        card.on(
                            "click",
                            lambda _, x=item: ui.navigate.to(
                                f"/stock/{x['market']}/"
                                f"{quote(x['exchange'], safe='')}/"
                                f"{quote(x['symbol'], safe='')}"
                            ),
                        )

                        with ui.row().classes(
                            "w-full items-start justify-between"
                        ):
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

                        price_label = ui.label(
                            "불러오는 중..."
                        ).classes(
                            "text-3xl font-black text-white mt-4"
                        )
                        change_label = ui.label("-").classes(
                            "text-sm font-bold text-slate-400"
                        )

                        spark_host = ui.column().classes(
                            "w-full h-[82px] mt-3"
                        )
                        with spark_host:
                            ui.label("30일 차트 불러오는 중...").classes(
                                "text-xs text-slate-600 mt-6"
                            )

                        with ui.row().classes(
                            "w-full items-center justify-between mt-3 pt-3 "
                            "border-t border-slate-800"
                        ):
                            ui.label("클릭해서 상세 차트").classes(
                                "text-xs text-slate-500"
                            )
                            last_time = ui.label("-").classes(
                                "text-xs text-slate-400"
                            )

                        async def delete_item(event, current=item):
                            try:
                                event.stop_propagation()
                            except Exception:
                                pass
                            await asyncio.to_thread(
                                delete_watchlist,
                                app.storage.user,
                                current["market"],
                                current["exchange"],
                                current["symbol"],
                            )
                            watchlist_items[:] = [
                                x for x in watchlist_items
                                if not (
                                    x["market"] == current["market"]
                                    and x["exchange"] == current["exchange"]
                                    and x["symbol"] == current["symbol"]
                                )
                            ]
                            await render_watchlist()
                            await load_news()

                        ui.button(
                            "삭제", on_click=delete_item
                        ).props("flat dense").classes(
                            "w-full mt-2 text-slate-500"
                        )

                        quote_refs[key] = {
                            "price": price_label,
                            "change": change_label,
                            "time": last_time,
                            "spark": spark_host,
                            "item": item,
                        }

        await asyncio.gather(
            refresh_quotes(),
            load_sparklines(),
        )

    async def refresh_quotes():
        for refs in list(quote_refs.values()):
            item = refs["item"]
            try:
                q = await fetch_quote(item)
                currency = q.get("currency", "KRW")
                price = q.get("price")
                change = q.get("change")
                pct = q.get("change_percent")

                if currency == "KRW":
                    refs["price"].set_text(
                        "-" if price is None else f"{price:,.0f}원"
                    )
                    text = (
                        "-"
                        if change is None or pct is None
                        else f"{change:+,.0f}원 ({pct:+.2f}%)"
                    )
                else:
                    refs["price"].set_text(
                        "-" if price is None else f"${price:,.2f}"
                    )
                    text = (
                        "-"
                        if change is None or pct is None
                        else f"${change:+,.2f} ({pct:+.2f}%)"
                    )

                refs["change"].set_text(text)
                refs["time"].set_text(
                    datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S")
                )
                refs["change"].classes(
                    remove="text-red-400 text-blue-400 text-slate-400"
                )
                refs["change"].classes(
                    add=(
                        "text-red-400" if pct and pct > 0
                        else "text-blue-400" if pct and pct < 0
                        else "text-slate-400"
                    )
                )
            except Exception:
                refs["price"].set_text("조회 실패")

    async def load_sparklines():
        async def one(refs):
            item = refs["item"]
            svg = await asyncio.to_thread(
                get_sparkline_svg,
                item["market"],
                item["exchange"],
                item["symbol"],
            )
            refs["spark"].clear()
            with refs["spark"]:
                if svg:
                    ui.html(svg).classes("w-full")
                else:
                    ui.label("미니차트 없음").classes(
                        "text-xs text-slate-600 mt-6"
                    )

        await asyncio.gather(
            *(one(refs) for refs in quote_refs.values())
        )

    await render_watchlist()
    ui.timer(REFRESH_SECONDS, refresh_quotes)

    # MACRO
    with macro_container:
        ui.label("주요 경제지표").classes(
            "text-lg font-bold text-white mb-3"
        )
        macro_grid = ui.grid(columns=4).classes(
            "w-full gap-3 max-md:grid-cols-2"
        )
        ui.label(
            "FRED 기준 · 발표주기에 따라 값의 시점이 다를 수 있습니다."
        ).classes("text-[11px] text-slate-600 mt-2")

    async def load_macro():
        data = await asyncio.to_thread(get_macro_overview)
        macro_grid.clear()
        with macro_grid:
            for item in data:
                value = item["value"]
                change = item["change"]
                color = (
                    "text-red-400"
                    if change is not None and change > 0
                    else "text-blue-400"
                    if change is not None and change < 0
                    else "text-slate-400"
                )
                with ui.card().classes("glass-card p-4"):
                    ui.label(item["name"]).classes(
                        "text-xs font-bold text-slate-500"
                    )
                    ui.label(
                        "-"
                        if value is None
                        else f"{value:.2f}{item['suffix']}"
                    ).classes("text-xl font-black text-white mt-1")
                    ui.label(
                        "-"
                        if change is None
                        else f"직전 대비 {change:+.2f}"
                    ).classes(f"text-xs {color}")

    await load_macro()
    ui.timer(900, load_macro)

    # NEWS
    with news_container:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("관심종목 뉴스").classes(
                "text-lg font-bold text-white"
            )
            news_status = ui.label("").classes(
                "text-xs text-slate-600"
            )
        news_list = ui.column().classes(
            "w-full glass-card mt-3 px-5"
        )

    async def load_news():
        news_status.set_text("업데이트 중...")
        data = await asyncio.to_thread(
            get_watchlist_news,
            watchlist_items,
            10,
        )
        news_list.clear()
        with news_list:
            if not data:
                ui.label(
                    "현재 표시할 관심종목 뉴스가 없습니다."
                ).classes("text-slate-500 py-5")
            for item in data:
                with ui.row().classes(
                    "w-full py-4 items-start justify-between "
                    "gap-4 news-row no-wrap"
                ):
                    with ui.column().classes("gap-1 min-w-0"):
                        if item["url"]:
                            ui.link(
                                item["title"],
                                item["url"],
                                new_tab=True,
                            ).classes(
                                "text-white font-semibold no-underline "
                                "hover:text-blue-400"
                            )
                        else:
                            ui.label(item["title"]).classes(
                                "text-white font-semibold"
                            )
                        meta = " · ".join(
                            x for x in [
                                item.get("symbol", ""),
                                item.get("publisher", ""),
                            ] if x
                        )
                        ui.label(meta).classes(
                            "text-xs text-slate-500"
                        )
        news_status.set_text(
            datetime.now(ZoneInfo("Asia/Seoul")).strftime(
                "%H:%M 업데이트"
            )
        )

    await load_news()
    ui.timer(300, load_news)


@ui.page(
    "/stock/{market}/{exchange}/{symbol}",
    response_timeout=15,
)
async def stock_detail(market: str, exchange: str, symbol: str):
    add_global_style()
    if not require_login():
        return

    # IMPORTANT: build the page before remote calls.
    with ui.row().classes(
        "w-full items-center justify-between sticky top-0 z-10 "
        "bg-[#07090d]/95 py-3"
    ):
        ui.button(
            "관심종목으로 돌아가기",
            icon="arrow_back",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat no-caps").classes(
            "text-blue-400 font-bold"
        )
        ui.button(
            icon="home",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat round")

    with ui.row().classes("w-full items-start justify-between mt-4"):
        with ui.column().classes("gap-0"):
            stock_name = ui.label(symbol).classes(
                "text-3xl font-black text-white"
            )
            ui.label(
                f"{symbol} · {exchange} · {market}"
            ).classes("text-sm text-slate-500")
        with ui.row().classes(
            "items-center gap-2 px-3 py-2 rounded-full "
            "border border-slate-800 bg-slate-900"
        ):
            ui.html('<div class="live-dot"></div>')
            ui.label("MARKET DATA").classes(
                "text-xs font-bold text-slate-200"
            )

    with ui.card().classes("glass-card p-5 mt-6 min-w-[280px]"):
        current_price = ui.label("가격 불러오는 중...").classes(
            "text-3xl font-black text-white"
        )
        current_change = ui.label("-").classes(
            "text-sm font-bold text-slate-400"
        )

    ui.label("차트").classes(
        "text-lg font-bold text-white mt-8 mb-2"
    )
    timeframe = ui.toggle(
        {"1D": "1일", "D": "일봉", "W": "주봉", "M": "월봉"},
        value="D",
    ).props("unelevated").classes("mb-3")

    ma_select = ui.select(
        options={5: "MA5", 20: "MA20", 60: "MA60", 120: "MA120"},
        value=[5, 20, 60, 120],
        multiple=True,
        label="이동평균선",
    ).props("outlined dark use-chips").classes(
        "w-full max-w-xl mb-4"
    )

    chart_container = ui.column().classes(
        "w-full chart-wrap min-h-[560px]"
    )
    with chart_container:
        ui.spinner(size="lg").classes("m-auto mt-24")
        ui.label("차트 데이터를 불러오는 중...").classes(
            "text-slate-500 m-auto"
        )

    ui.button(
        "관심종목으로 돌아가기",
        icon="arrow_back",
        on_click=lambda: ui.navigate.to("/"),
    ).props("outline no-caps").classes(
        "mt-6 mb-10 text-blue-400"
    )

    await ui.context.client.connected()

    try:
        await asyncio.to_thread(get_user, app.storage.user)
        items = await asyncio.to_thread(
            load_watchlist, app.storage.user
        )
        stock = next(
            (
                x for x in items
                if x["market"] == market
                and x["exchange"] == exchange
                and x["symbol"] == symbol
            ),
            None,
        )
        if stock:
            stock_name.set_text(stock["name"])
    except Exception:
        clear_session()
        ui.navigate.to("/login")
        return

    async def refresh_header():
        try:
            if market == "KR":
                q = await asyncio.to_thread(
                    kis.get_domestic_quote, symbol
                )
            else:
                q = await asyncio.to_thread(
                    get_us_quote, symbol
                )
            currency = q.get("currency", "KRW")
            price = q.get("price")
            change = q.get("change")
            pct = q.get("change_percent")

            if currency == "KRW":
                current_price.set_text(
                    "-" if price is None else f"{price:,.0f}원"
                )
                text = (
                    "-" if change is None or pct is None
                    else f"{change:+,.0f}원 ({pct:+.2f}%)"
                )
            else:
                current_price.set_text(
                    "-" if price is None else f"${price:,.2f}"
                )
                text = (
                    "-" if change is None or pct is None
                    else f"${change:+,.2f} ({pct:+.2f}%)"
                )
            current_change.set_text(text)
        except Exception as exc:
            current_price.set_text("조회 실패")
            current_change.set_text(str(exc)[:100])

    chart_lock = asyncio.Lock()

    async def render_chart():
        if chart_lock.locked():
            return
        async with chart_lock:
            chart_container.clear()
            with chart_container:
                ui.spinner(size="lg").classes("m-auto mt-24")
                ui.label(
                    f"{timeframe.value} 차트를 불러오는 중..."
                ).classes("text-slate-500 m-auto")
            try:
                figure = await asyncio.to_thread(
                    get_chart_figure,
                    kis,
                    market,
                    exchange,
                    symbol,
                    timeframe.value,
                    tuple(ma_select.value or []),
                )
                chart_container.clear()
                with chart_container:
                    ui.plotly(figure).classes(
                        "w-full h-[620px]"
                    )
            except Exception as exc:
                chart_container.clear()
                with chart_container:
                    ui.label(
                        f"차트 조회 실패: {exc}"
                    ).classes("text-red-400 p-6")

    timeframe.on(
        "update:model-value",
        lambda _: render_chart(),
        throttle=0.2,
        leading_events=False,
        trailing_events=True,
    )
    ma_select.on(
        "update:model-value",
        lambda _: render_chart(),
        throttle=0.2,
        leading_events=False,
        trailing_events=True,
    )

    await asyncio.gather(
        refresh_header(),
        render_chart(),
    )
    ui.timer(REFRESH_SECONDS, refresh_header)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "my-market",
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
    storage_secret=STORAGE_SECRET,
)
