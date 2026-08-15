import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv
from nicegui import app, ui

from kis import KISClient
from market_data import get_us_quote, search_stocks
from supabase_store import (
    SupabaseNotConfigured,
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
                background: rgba(15, 20, 28, .92) !important;
                border: 1px solid rgba(71, 85, 105, .35) !important;
                border-radius: 18px !important;
                box-shadow: none !important;
            }
            .stock-card { min-height: 250px; }
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


def is_logged_in() -> bool:
    return bool(
        app.storage.user.get("access_token")
        and app.storage.user.get("refresh_token")
    )


def save_session(auth_result) -> None:
    session = auth_result.session
    user = auth_result.user

    if session:
        app.storage.user["access_token"] = session.access_token
        app.storage.user["refresh_token"] = session.refresh_token

    if user:
        app.storage.user["user_id"] = str(user.id)
        app.storage.user["email"] = user.email or ""


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


@ui.page("/login")
def login_page():
    add_global_style()

    if is_logged_in():
        ui.navigate.to("/")
        return

    with ui.column().classes(
        "w-full min-h-[80vh] items-center justify-center"
    ):
        with ui.card().classes("glass-card w-full max-w-md p-8"):
            ui.label("MY MARKET").classes(
                "text-3xl font-black tracking-tight text-white"
            )
            ui.label("개인 투자 대시보드에 로그인").classes(
                "text-slate-400 mb-5"
            )

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
                    ui.notify("이메일과 비밀번호를 입력해주세요.", type="warning")
                    return

                try:
                    result = await asyncio.to_thread(
                        sign_in,
                        email.value.strip(),
                        password.value,
                    )
                    save_session(result)
                    ui.notify("로그인했습니다.", type="positive")
                    ui.navigate.to("/")
                except Exception as exc:
                    ui.notify(f"로그인 실패: {exc}", type="negative")

            ui.button(
                "로그인",
                on_click=handle_login,
            ).props("unelevated").classes(
                "w-full h-12 add-button text-base font-bold mt-2"
            )

            ui.separator().classes("my-4 bg-slate-800")

            with ui.row().classes("w-full justify-center items-center gap-1"):
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
        "w-full min-h-[80vh] items-center justify-center"
    ):
        with ui.card().classes("glass-card w-full max-w-md p-8"):
            ui.label("MY MARKET").classes(
                "text-3xl font-black tracking-tight text-white"
            )
            ui.label("새 계정 만들기").classes("text-slate-400 mb-5")

            display_name = ui.input(
                "표시 이름",
                placeholder="예: 홍길동",
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
                    ui.notify("이메일과 비밀번호를 입력해주세요.", type="warning")
                    return

                if password.value != confirm.value:
                    ui.notify("비밀번호가 서로 다릅니다.", type="warning")
                    return

                if len(password.value) < 8:
                    ui.notify("비밀번호는 8자 이상을 권장합니다.", type="warning")
                    return

                try:
                    result = await asyncio.to_thread(
                        sign_up,
                        email.value.strip(),
                        password.value,
                        (display_name.value or "").strip(),
                    )

                    if result.session:
                        save_session(result)
                        ui.notify("가입이 완료되었습니다.", type="positive")
                        ui.navigate.to("/")
                    else:
                        ui.notify(
                            "가입되었습니다. 이메일 인증 링크를 확인한 뒤 로그인해주세요.",
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
                "w-full h-12 add-button text-base font-bold mt-2"
            )

            with ui.row().classes("w-full justify-center items-center gap-1 mt-3"):
                ui.label("이미 계정이 있으신가요?").classes("text-slate-500")
                ui.link("로그인", "/login").classes(
                    "text-blue-400 font-bold no-underline"
                )


@ui.page("/")
async def dashboard():
    add_global_style()

    if not require_login():
        return

    try:
        user = await asyncio.to_thread(get_user, app.storage.user)
        if not user:
            raise RuntimeError("사용자 정보를 확인할 수 없습니다.")
        profile = await asyncio.to_thread(get_profile, app.storage.user)
    except Exception:
        clear_session()
        ui.navigate.to("/login")
        return

    display_name = (
        (profile or {}).get("display_name")
        or app.storage.user.get("email")
        or "User"
    )
    app.storage.user["display_name"] = display_name

    try:
        items = await asyncio.to_thread(load_watchlist, app.storage.user)
    except Exception as exc:
        items = []
        ui.notify(f"관심종목 불러오기 실패: {exc}", type="negative")

    quote_refs: dict[str, dict] = {}
    watchlist_items = list(items)

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

    def format_price(value, currency):
        if value is None:
            return "-"
        if currency == "KRW":
            return f"{value:,.0f}원"
        return f"${value:,.2f}"

    def format_change(change, percent, currency):
        if change is None or percent is None:
            return "-"
        prefix = "+" if change > 0 else ""
        if currency == "KRW":
            return f"{prefix}{change:,.0f}원 ({prefix}{percent:.2f}%)"
        return f"{prefix}${change:,.2f} ({prefix}{percent:.2f}%)"

    async def refresh_quotes():
        for item in list(watchlist_items):
            key = f"{item['market']}:{item['exchange']}:{item['symbol']}"
            refs = quote_refs.get(key)
            if not refs:
                continue

            try:
                quote = await fetch_quote(item)
                currency = quote.get("currency", "KRW")
                refs["price"].set_text(
                    format_price(quote.get("price"), currency)
                )
                refs["change"].set_text(
                    format_change(
                        quote.get("change"),
                        quote.get("change_percent"),
                        currency,
                    )
                )
                refs["time"].set_text(datetime.now().strftime("%H:%M:%S"))

                percent = quote.get("change_percent")
                refs["change"].classes(
                    remove="text-red-400 text-blue-400 text-slate-400"
                )
                if percent is None or percent == 0:
                    refs["change"].classes(add="text-slate-400")
                elif percent > 0:
                    refs["change"].classes(add="text-red-400")
                else:
                    refs["change"].classes(add="text-blue-400")

            except Exception as exc:
                refs["price"].set_text("조회 실패")
                refs["change"].set_text(str(exc)[:80])
                refs["change"].classes(
                    remove="text-red-400 text-blue-400",
                    add="text-slate-400",
                )

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
                "items-center gap-2 px-3 py-2 rounded-full border "
                "border-slate-800 bg-slate-900"
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
            ui.label("ACCOUNT").classes("text-xs font-bold text-slate-500")
            ui.label(display_name).classes(
                "text-xl font-bold text-white mt-2 truncate"
            )
            ui.label("Supabase Auth").classes("text-xs text-slate-500")

        with ui.card().classes("glass-card p-5"):
            ui.label("KIS").classes("text-xs font-bold text-slate-500")
            ui.label(
                "CONNECTED" if kis.enabled() else "NOT CONFIGURED"
            ).classes("text-xl font-bold text-white mt-2")
            ui.label("한국주식 시세").classes("text-xs text-slate-500")

        with ui.card().classes("glass-card p-5"):
            ui.label("WATCHLIST").classes("text-xs font-bold text-slate-500")
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
                    ui.label("검색창에서 종목을 추가해보세요.").classes(
                        "text-slate-400"
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

                    with ui.card().classes("glass-card stock-card p-5"):
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

                        price = ui.label("불러오는 중...").classes(
                            "text-3xl font-black tracking-tight mt-6 text-white"
                        )
                        change = ui.label("-").classes(
                            "text-sm font-bold text-slate-400 mt-1"
                        )

                        with ui.row().classes(
                            "w-full items-center justify-between mt-6 pt-4 "
                            "border-t border-slate-800"
                        ):
                            ui.label("마지막 조회").classes(
                                "text-xs text-slate-500"
                            )
                            last_time = ui.label("-").classes(
                                "text-xs text-slate-400"
                            )

                        async def delete_item(
                            current=item,
                        ):
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
                                ui.notify(
                                    "관심종목에서 삭제했습니다.",
                                    type="positive",
                                )
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
                            "price": price,
                            "change": change,
                            "time": last_time,
                        }

        await refresh_quotes()

    async def do_search():
        results_container.clear()
        q = (search_input.value or "").strip()
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
                ui.label("검색 결과가 없습니다.").classes("text-slate-400")
                return

            with ui.column().classes("w-full gap-2"):
                for item in results[:10]:
                    with ui.card().classes("w-full glass-card px-4 py-3"):
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
                                try:
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

                                    ui.notify(
                                        f"{current['name']} 추가",
                                        type="positive",
                                    )
                                    await render_watchlist()
                                except Exception as exc:
                                    ui.notify(
                                        f"추가 실패: {exc}",
                                        type="negative",
                                    )

                            ui.button(
                                "추가",
                                icon="add",
                                on_click=add_item,
                            ).props("unelevated").classes("add-button")

    search_input.on("keydown.enter", do_search)
    await render_watchlist()

    ui.timer(REFRESH_SECONDS, refresh_quotes)


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
