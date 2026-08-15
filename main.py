import asyncio
import json
import os
from datetime import datetime
from urllib.parse import parse_qs, quote

from dotenv import load_dotenv
from nicegui import app, ui

from chart_data import get_chart_figure
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

kis = KISClient(
    app_key=KIS_APP_KEY,
    app_secret=KIS_APP_SECRET,
    env=KIS_ENV,
)


def add_global_style() -> None:
    ui.add_head_html(
        """
        <style>
            body {
                background:
                    radial-gradient(circle at top left, rgba(26,42,70,.35), transparent 32%),
                    #07090d;
                color: #f8fafc;
            }
            .nicegui-content {
                max-width: 1220px;
                margin: 0 auto;
                padding: 30px 24px 70px 24px;
            }
            .glass-card {
                background: rgba(15,20,28,.92) !important;
                border: 1px solid rgba(71,85,105,.35) !important;
                border-radius: 18px !important;
                box-shadow: none !important;
            }
            .stock-card {
                min-height: 250px;
                cursor: pointer;
                transition: transform .15s ease, border-color .15s ease;
            }
            .stock-card:hover {
                transform: translateY(-2px);
                border-color: rgba(96,165,250,.6) !important;
            }
            .market-pill {
                background: #171d27;
                color: #94a3b8;
                border: 1px solid #273244;
                padding: 5px 8px;
                border-radius: 8px;
            }
            .search-box .q-field__control,
            .auth-input .q-field__control {
                background: #0e131b !important;
                border-radius: 14px !important;
            }
            .primary-button {
                background: #2563eb !important;
                border-radius: 10px !important;
            }
            .social-button {
                border: 1px solid #334155 !important;
                border-radius: 12px !important;
                min-height: 46px;
                background: #111827 !important;
                color: #f8fafc !important;
            }
            .kakao-button {
                background: #fee500 !important;
                color: #111827 !important;
                border-color: #fee500 !important;
            }
            .naver-button {
                background: #03c75a !important;
                color: white !important;
                border-color: #03c75a !important;
            }
            .live-dot {
                width: 8px;
                height: 8px;
                border-radius: 999px;
                background: #4ade80;
                box-shadow: 0 0 14px rgba(74,222,128,.65);
            }
            .chart-wrap {
                background: rgba(15,20,28,.92);
                border: 1px solid rgba(71,85,105,.35);
                border-radius: 18px;
                overflow: hidden;
            }
        </style>
        """
    )


def is_logged_in() -> bool:
    return bool(
        app.storage.user.get("access_token")
        and app.storage.user.get("refresh_token")
    )


def save_session_tokens(access_token: str, refresh_token: str) -> None:
    app.storage.user["access_token"] = access_token
    app.storage.user["refresh_token"] = refresh_token


def save_auth_result(result) -> None:
    if result.session:
        save_session_tokens(
            result.session.access_token,
            result.session.refresh_token,
        )
    if result.user:
        app.storage.user["user_id"] = str(result.user.id)
        app.storage.user["email"] = result.user.email or ""


def clear_session() -> None:
    for key in [
        "access_token",
        "refresh_token",
        "user_id",
        "email",
        "display_name",
    ]:
        app.storage.user.pop(key, None)


def require_login() -> bool:
    if not is_logged_in():
        ui.navigate.to("/login")
        return False
    return True


def social_auth_url(provider: str) -> str:
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL이 설정되지 않았습니다.")
    if not APP_URL:
        raise RuntimeError("APP_URL이 설정되지 않았습니다.")

    redirect_to = f"{APP_URL}/oauth/callback"
    return (
        f"{SUPABASE_URL}/auth/v1/authorize"
        f"?provider={quote(provider, safe=':')}"
        f"&redirect_to={quote(redirect_to, safe='')}"
    )


async def go_social(provider: str) -> None:
    try:
        url = social_auth_url(provider)
        await ui.run_javascript(
            f"window.location.assign({json.dumps(url)});"
        )
    except Exception as exc:
        ui.notify(f"소셜 로그인 설정 오류: {exc}", type="negative")


def social_buttons() -> None:
    if ENABLE_GOOGLE:
        ui.button(
            "Google로 계속하기",
            icon="login",
            on_click=lambda: go_social("google"),
        ).props("unelevated").classes("w-full social-button")

    if ENABLE_KAKAO:
        ui.button(
            "카카오로 계속하기",
            icon="chat",
            on_click=lambda: go_social("kakao"),
        ).props("unelevated").classes("w-full social-button kakao-button")

    if ENABLE_NAVER:
        ui.button(
            "네이버로 계속하기",
            icon="account_circle",
            on_click=lambda: go_social("custom:naver"),
        ).props("unelevated").classes("w-full social-button naver-button")

    if ENABLE_APPLE:
        ui.button(
            "Apple로 계속하기",
            icon="apple",
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

            email = ui.input(
                "이메일",
                placeholder="you@example.com",
            ).props("outlined dark").classes("w-full auth-input")

            password = ui.input(
                "비밀번호",
                password=True,
                password_toggle_button=True,
            ).props("outlined dark").classes("w-full auth-input")

            async def handle_login():
                if not email.value or not password.value:
                    ui.notify(
                        "이메일과 비밀번호를 입력해주세요.",
                        type="warning",
                    )
                    return
                try:
                    result = await asyncio.to_thread(
                        sign_in,
                        email.value.strip(),
                        password.value,
                    )
                    save_auth_result(result)
                    ui.navigate.to("/")
                except Exception as exc:
                    ui.notify(f"로그인 실패: {exc}", type="negative")

            ui.button(
                "이메일로 로그인",
                on_click=handle_login,
            ).props("unelevated").classes(
                "w-full h-12 primary-button text-base font-bold mt-2"
            )

            with ui.row().classes(
                "w-full justify-center items-center gap-1 mt-4"
            ):
                ui.label("계정이 없으신가요?").classes("text-slate-500")
                ui.link("회원가입", "/signup").classes(
                    "text-blue-400 font-bold no-underline"
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
                "text-3xl font-black tracking-tight text-white"
            )
            ui.label("새 계정 만들기").classes(
                "text-slate-400 mb-5"
            )

            display_name = ui.input(
                "표시 이름",
                placeholder="예: DJ",
            ).props("outlined dark").classes("w-full auth-input")

            email = ui.input(
                "이메일",
                placeholder="you@example.com",
            ).props("outlined dark").classes("w-full auth-input")

            password = ui.input(
                "비밀번호",
                password=True,
                password_toggle_button=True,
            ).props("outlined dark").classes("w-full auth-input")

            confirm = ui.input(
                "비밀번호 확인",
                password=True,
                password_toggle_button=True,
            ).props("outlined dark").classes("w-full auth-input")

            async def handle_signup():
                if not email.value or not password.value:
                    ui.notify(
                        "이메일과 비밀번호를 입력해주세요.",
                        type="warning",
                    )
                    return
                if password.value != confirm.value:
                    ui.notify("비밀번호가 서로 다릅니다.", type="warning")
                    return
                if len(password.value) < 8:
                    ui.notify("비밀번호는 8자 이상으로 해주세요.", type="warning")
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
                            "가입되었습니다. 인증 메일을 확인한 뒤 로그인해주세요.",
                            type="positive",
                            timeout=8000,
                        )
                        ui.navigate.to("/login")
                except Exception as exc:
                    ui.notify(f"회원가입 실패: {exc}", type="negative")

            ui.button(
                "회원가입",
                on_click=handle_signup,
            ).props("unelevated").classes(
                "w-full h-12 primary-button text-base font-bold mt-2"
            )

            ui.link("로그인으로 돌아가기", "/login").classes(
                "w-full text-center text-blue-400 mt-4 no-underline"
            )


@ui.page("/oauth/callback")
def oauth_callback():
    """Supabase implicit OAuth callback.

    Supabase returns access/refresh tokens in the URL fragment.
    The fragment is readable only in the browser, so NiceGUI JS reads it
    and passes the result back into this user's NiceGUI session.
    """
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
            query_value = await ui.run_javascript(
                "window.location.search || ''"
            )

            if hash_value:
                params = parse_qs(str(hash_value).lstrip("#"))
                error = params.get("error_description", params.get("error", [None]))[0]
                if error:
                    ui.notify(f"소셜 로그인 실패: {error}", type="negative")
                    ui.navigate.to("/login")
                    return

                access_token = params.get("access_token", [None])[0]
                refresh_token = params.get("refresh_token", [None])[0]

                if access_token and refresh_token:
                    save_session_tokens(access_token, refresh_token)
                    ui.navigate.to("/")
                    return

            # This app intentionally uses Supabase's browser implicit OAuth flow.
            # If a project is configured to return ?code= (PKCE), show a clear hint.
            if "code=" in str(query_value):
                ui.notify(
                    "Supabase가 PKCE code를 반환했습니다. "
                    "Auth flow 설정을 implicit으로 확인해주세요.",
                    type="warning",
                    timeout=8000,
                )
                return

            ui.notify(
                "로그인 토큰을 찾지 못했습니다.",
                type="negative",
            )
            ui.navigate.to("/login")
        except Exception as exc:
            ui.notify(f"OAuth 처리 실패: {exc}", type="negative")
            ui.navigate.to("/login")

    ui.timer(0.5, finalize, once=True)


async def get_current_user_and_profile():
    user = await asyncio.to_thread(get_user, app.storage.user)
    profile = await asyncio.to_thread(get_profile, app.storage.user)
    return user, profile


@ui.page("/")
async def dashboard():
    add_global_style()
    if not require_login():
        return

    try:
        user, profile = await get_current_user_and_profile()
        if not user:
            raise RuntimeError("사용자 정보를 확인할 수 없습니다.")
    except Exception:
        clear_session()
        ui.navigate.to("/login")
        return

    display_name = (
        (profile or {}).get("display_name")
        or app.storage.user.get("email")
        or "User"
    )

    try:
        watchlist_items = await asyncio.to_thread(
            load_watchlist,
            app.storage.user,
        )
    except Exception as exc:
        watchlist_items = []
        ui.notify(f"관심종목 불러오기 실패: {exc}", type="negative")

    quote_refs = {}

    async def fetch_quote(item):
        if item["market"] == "KR":
            return await asyncio.to_thread(
                kis.get_domestic_quote,
                item["symbol"],
            )
        return await asyncio.to_thread(
            get_us_quote,
            item["symbol"],
        )

    def fmt_price(value, currency):
        if value is None:
            return "-"
        return (
            f"{value:,.0f}원"
            if currency == "KRW"
            else f"${value:,.2f}"
        )

    def fmt_change(change, percent, currency):
        if change is None or percent is None:
            return "-"
        prefix = "+" if change > 0 else ""
        amount = (
            f"{prefix}{change:,.0f}원"
            if currency == "KRW"
            else f"{prefix}${change:,.2f}"
        )
        return f"{amount} ({prefix}{percent:.2f}%)"

    async def refresh_quotes():
        for item in list(watchlist_items):
            key = (
                f"{item['market']}:"
                f"{item['exchange']}:"
                f"{item['symbol']}"
            )
            refs = quote_refs.get(key)
            if not refs:
                continue
            try:
                q = await fetch_quote(item)
                currency = q.get("currency", "KRW")
                refs["price"].set_text(
                    fmt_price(q.get("price"), currency)
                )
                refs["change"].set_text(
                    fmt_change(
                        q.get("change"),
                        q.get("change_percent"),
                        currency,
                    )
                )
                refs["time"].set_text(
                    datetime.now().strftime("%H:%M:%S")
                )

                pct = q.get("change_percent")
                refs["change"].classes(
                    remove="text-red-400 text-blue-400 text-slate-400"
                )
                if pct is None or pct == 0:
                    refs["change"].classes(add="text-slate-400")
                elif pct > 0:
                    refs["change"].classes(add="text-red-400")
                else:
                    refs["change"].classes(add="text-blue-400")
            except Exception as exc:
                refs["price"].set_text("조회 실패")
                refs["change"].set_text(str(exc)[:80])

    async def logout():
        try:
            await asyncio.to_thread(sign_out, app.storage.user)
        except Exception:
            pass
        clear_session()
        ui.navigate.to("/login")

    with ui.row().classes("w-full items-center justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("PERSONAL INVESTMENT TERMINAL").classes(
                "text-[11px] tracking-[.18em] font-bold text-slate-500"
            )
            ui.label("MY MARKET").classes(
                "text-4xl font-black tracking-tight text-white"
            )

        with ui.row().classes("items-center gap-3"):
            with ui.row().classes(
                "items-center gap-2 px-3 py-2 rounded-full "
                "border border-slate-800 bg-slate-900"
            ):
                ui.html('<div class="live-dot"></div>')
                ui.label("ONLINE").classes(
                    "text-xs font-bold text-slate-200"
                )
            with ui.button(icon="account_circle").props(
                "flat round color=grey"
            ):
                with ui.menu():
                    ui.label(display_name).classes(
                        "font-bold px-4 pt-3 text-slate-800"
                    )
                    ui.label(app.storage.user.get("email", "")).classes(
                        "text-xs px-4 pb-2 text-slate-500"
                    )
                    ui.separator()
                    ui.menu_item("로그아웃", logout)

    with ui.grid(columns=3).classes(
        "w-full gap-3 mt-8 max-md:grid-cols-1"
    ):
        with ui.card().classes("glass-card p-5"):
            ui.label("ACCOUNT").classes(
                "text-xs font-bold text-slate-500"
            )
            ui.label(display_name).classes(
                "text-xl font-bold text-white mt-2 truncate"
            )
            ui.label("Supabase Auth").classes("text-xs text-slate-500")

        with ui.card().classes("glass-card p-5"):
            ui.label("KIS").classes(
                "text-xs font-bold text-slate-500"
            )
            ui.label(
                "CONNECTED" if kis.enabled() else "NOT CONFIGURED"
            ).classes("text-xl font-bold text-white mt-2")
            ui.label("한국주식 시세").classes("text-xs text-slate-500")

        with ui.card().classes("glass-card p-5"):
            ui.label("WATCHLIST").classes(
                "text-xs font-bold text-slate-500"
            )
            watch_count = ui.label(str(len(watchlist_items))).classes(
                "text-xl font-bold text-white mt-2"
            )
            ui.label("내 관심종목").classes("text-xs text-slate-500")

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
                    ui.label(
                        "검색창에서 종목을 추가해보세요."
                    ).classes("text-slate-400")
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
                            "text-3xl font-black tracking-tight "
                            "mt-6 text-white"
                        )
                        change_label = ui.label("-").classes(
                            "text-sm font-bold text-slate-400 mt-1"
                        )

                        with ui.row().classes(
                            "w-full items-center justify-between mt-6 pt-4 "
                            "border-t border-slate-800"
                        ):
                            ui.label(
                                "클릭해서 차트 보기"
                            ).classes("text-xs text-slate-500")
                            last_time = ui.label("-").classes(
                                "text-xs text-slate-400"
                            )

                        async def delete_item(
                            event,
                            current=item,
                        ):
                            # Prevent card click from navigating.
                            try:
                                event.stop_propagation()
                            except Exception:
                                pass
                            try:
                                await asyncio.to_thread(
                                    delete_watchlist,
                                    app.storage.user,
                                    current["market"],
                                    current["exchange"],
                                    current["symbol"],
                                )
                                watchlist_items[:] = [
                                    x
                                    for x in watchlist_items
                                    if not (
                                        x["market"] == current["market"]
                                        and x["exchange"] == current["exchange"]
                                        and x["symbol"] == current["symbol"]
                                    )
                                ]
                                await render_watchlist()
                            except Exception as exc:
                                ui.notify(
                                    f"삭제 실패: {exc}",
                                    type="negative",
                                )

                        ui.button(
                            "삭제",
                            on_click=delete_item,
                        ).props("flat dense").classes(
                            "w-full mt-3 text-slate-500 hover:text-white"
                        )

                        quote_refs[key] = {
                            "price": price_label,
                            "change": change_label,
                            "time": last_time,
                        }

        await refresh_quotes()

    async def do_search():
        results_container.clear()
        q = (search_input.value or "").strip()
        if not q:
            return

        results = await asyncio.to_thread(search_stocks, q)
        with results_container:
            if not results:
                ui.label("검색 결과가 없습니다.").classes(
                    "text-slate-400"
                )
                return

            with ui.column().classes("w-full gap-2"):
                for item in results[:10]:
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
                                await render_watchlist()

                            ui.button(
                                "추가",
                                icon="add",
                                on_click=add_item,
                            ).props("unelevated").classes("primary-button")

    search_input.on("keydown.enter", do_search)
    await render_watchlist()
    ui.timer(REFRESH_SECONDS, refresh_quotes)


@ui.page("/stock/{market}/{exchange}/{symbol}")
async def stock_detail(market: str, exchange: str, symbol: str):
    add_global_style()
    if not require_login():
        return

    try:
        await asyncio.to_thread(get_user, app.storage.user)
        items = await asyncio.to_thread(
            load_watchlist,
            app.storage.user,
        )
    except Exception:
        clear_session()
        ui.navigate.to("/login")
        return

    stock = next(
        (
            x for x in items
            if x["market"] == market
            and x["exchange"] == exchange
            and x["symbol"] == symbol
        ),
        {
            "market": market,
            "exchange": exchange,
            "symbol": symbol,
            "name": symbol,
        },
    )

    with ui.row().classes("w-full items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.button(
                icon="arrow_back",
                on_click=lambda: ui.navigate.to("/"),
            ).props("flat round")
            with ui.column().classes("gap-0"):
                ui.label(stock["name"]).classes(
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

    quote_container = ui.row().classes("w-full mt-6")
    with quote_container:
        with ui.card().classes("glass-card p-5 min-w-[280px]"):
            current_price = ui.label("불러오는 중...").classes(
                "text-3xl font-black text-white"
            )
            current_change = ui.label("-").classes(
                "text-sm font-bold text-slate-400"
            )

    async def refresh_header():
        try:
            if market == "KR":
                q = await asyncio.to_thread(
                    kis.get_domestic_quote,
                    symbol,
                )
            else:
                q = await asyncio.to_thread(
                    get_us_quote,
                    symbol,
                )

            currency = q.get("currency", "KRW")
            price = q.get("price")
            change = q.get("change")
            pct = q.get("change_percent")

            if currency == "KRW":
                current_price.set_text(
                    "-" if price is None else f"{price:,.0f}원"
                )
                change_text = (
                    "-"
                    if change is None or pct is None
                    else f"{change:+,.0f}원 ({pct:+.2f}%)"
                )
            else:
                current_price.set_text(
                    "-" if price is None else f"${price:,.2f}"
                )
                change_text = (
                    "-"
                    if change is None or pct is None
                    else f"{change:+,.2f} ({pct:+.2f}%)"
                )

            current_change.set_text(change_text)
            current_change.classes(
                remove="text-red-400 text-blue-400 text-slate-400"
            )
            if pct is None or pct == 0:
                current_change.classes(add="text-slate-400")
            elif pct > 0:
                current_change.classes(add="text-red-400")
            else:
                current_change.classes(add="text-blue-400")
        except Exception as exc:
            current_price.set_text("조회 실패")
            current_change.set_text(str(exc)[:100])

    ui.label("차트").classes(
        "text-lg font-bold text-white mt-8 mb-2"
    )

    timeframe = ui.toggle(
        {
            "1D": "1일",
            "D": "일봉",
            "W": "주봉",
            "M": "월봉",
        },
        value="D",
    ).props("unelevated").classes("mb-3")

    ma_select = ui.select(
        options={
            5: "MA5",
            20: "MA20",
            60: "MA60",
            120: "MA120",
        },
        value=[5, 20, 60, 120],
        multiple=True,
        label="이동평균선",
    ).props(
        "outlined dark use-chips"
    ).classes("w-full max-w-xl mb-4")

    chart_container = ui.column().classes(
        "w-full chart-wrap min-h-[560px]"
    )

    loading = False

    async def render_chart():
        nonlocal loading
        if loading:
            return
        loading = True
        chart_container.clear()

        with chart_container:
            spinner = ui.spinner(size="lg").classes("m-auto mt-20")

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
                ui.plotly(figure).classes("w-full h-[620px]")
        except Exception as exc:
            chart_container.clear()
            with chart_container:
                ui.label(
                    f"차트 조회 실패: {exc}"
                ).classes("text-red-400 p-6")
        finally:
            loading = False

    timeframe.on("update:model-value", lambda _: render_chart())
    ma_select.on("update:model-value", lambda _: render_chart())

    await refresh_header()
    await render_chart()
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
