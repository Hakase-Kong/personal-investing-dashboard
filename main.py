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
from public_data import get_representative_stocks, sparkline_svg
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


def add_style():
    ui.add_head_html(
        """
        <style>
            body {
                background:
                    radial-gradient(circle at 15% 0%, rgba(29,78,216,.13), transparent 26%),
                    #07090d;
                color:#f8fafc;
            }
            .nicegui-content {
                max-width:1240px;
                margin:0 auto;
                padding:24px 24px 72px;
            }
            .glass {
                background:rgba(15,20,28,.91)!important;
                border:1px solid rgba(71,85,105,.35)!important;
                border-radius:18px!important;
                box-shadow:none!important;
            }
            .hero {
                background:
                    radial-gradient(circle at 80% 15%, rgba(14,165,233,.17), transparent 33%),
                    linear-gradient(135deg, rgba(15,23,42,.97), rgba(8,12,19,.98));
                border:1px solid rgba(71,85,105,.34);
                border-radius:24px;
            }
            .stock-card {
                cursor:pointer;
                transition:transform .15s ease,border-color .15s ease;
            }
            .stock-card:hover {
                transform:translateY(-2px);
                border-color:rgba(96,165,250,.62)!important;
            }
            .pill {
                background:#111827;
                border:1px solid #263244;
                border-radius:999px;
                padding:6px 11px;
                color:#94a3b8;
            }
            .search-box .q-field__control,.auth-input .q-field__control {
                background:#0d121a!important;
                border-radius:13px!important;
            }
            .primary { background:#2563eb!important; border-radius:11px!important; }
            .social {
                border-radius:12px!important;
                min-height:48px;
                font-weight:700!important;
            }
            .social-google {
                background:#1b2028!important;
                color:#f8fafc!important;
                border:1px solid #343b48!important;
            }
            .social-kakao {
                background:#fee500!important;
                color:#171717!important;
            }
            .social-naver {
                background:#03c75a!important;
                color:white!important;
            }
            .social-apple {
                background:#f5f5f7!important;
                color:#0b0b0c!important;
            }
            .live-dot {
                width:8px;height:8px;border-radius:999px;background:#4ade80;
                box-shadow:0 0 12px rgba(74,222,128,.65);
            }
            .chart-wrap {
                background:rgba(15,20,28,.92);
                border:1px solid rgba(71,85,105,.35);
                border-radius:18px;
                overflow:hidden;
            }
            .section-title { font-size:1.15rem; font-weight:800; color:#fff; }
        </style>
        """
    )


def logged_in():
    return bool(
        app.storage.user.get("access_token")
        and app.storage.user.get("refresh_token")
    )


def clear_session():
    for k in [
        "access_token", "refresh_token", "user_id",
        "email", "display_name",
    ]:
        app.storage.user.pop(k, None)


def save_auth_result(result):
    if result.session:
        app.storage.user["access_token"] = result.session.access_token
        app.storage.user["refresh_token"] = result.session.refresh_token
    if result.user:
        app.storage.user["user_id"] = str(result.user.id)
        app.storage.user["email"] = result.user.email or ""


def require_login():
    if not logged_in():
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


async def social_login(provider):
    await ui.run_javascript(
        f"window.location.assign({json.dumps(social_auth_url(provider))});"
    )


def header(public=True):
    with ui.row().classes("w-full items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.label("MY MARKET").classes(
                "text-2xl font-black tracking-tight text-white"
            )
            if public:
                ui.label("PUBLIC").classes("pill text-[10px] font-bold")
        with ui.row().classes("items-center gap-3"):
            kst = ui.label("--:-- KST").classes(
                "text-sm font-bold text-slate-300 tabular-nums"
            )
            if logged_in():
                ui.button(
                    "내 대시보드",
                    icon="dashboard",
                    on_click=lambda: ui.navigate.to("/dashboard"),
                ).props("flat no-caps").classes("text-blue-400 font-bold")
            else:
                ui.button(
                    "로그인",
                    icon="login",
                    on_click=lambda: ui.navigate.to("/login"),
                ).props("outline no-caps").classes("text-slate-200")

    def tick():
        kst.set_text(
            datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S KST")
        )
    tick()
    ui.timer(1.0, tick)


def fmt_public_price(item):
    if item["market"] == "KR":
        return "-" if item["price"] is None else f"{item['price']:,.0f}원"
    return "-" if item["price"] is None else f"${item['price']:,.2f}"


@ui.page("/", response_timeout=15)
async def public_home():
    add_style()
    header(public=True)

    with ui.column().classes("w-full hero p-7 mt-6 gap-2"):
        ui.label("시장을 보고, 로그인하면 내 투자 화면으로.").classes(
            "text-3xl md:text-4xl font-black text-white"
        )
        ui.label(
            "한국·미국 대표 종목, 주요 지수, 경제지표와 뉴스를 로그인 없이 확인하세요."
        ).classes("text-slate-400 max-w-3xl")
        with ui.row().classes("gap-2 mt-4"):
            if logged_in():
                ui.button(
                    "내 관심종목 보기",
                    icon="star",
                    on_click=lambda: ui.navigate.to("/dashboard"),
                ).props("unelevated no-caps").classes("primary px-5")
            else:
                ui.button(
                    "개인화 시작하기",
                    icon="person",
                    on_click=lambda: ui.navigate.to("/login"),
                ).props("unelevated no-caps").classes("primary px-5")
            ui.button(
                "아래 시장 보기",
                icon="south",
                on_click=lambda: ui.run_javascript(
                    "window.scrollTo({top: 500, behavior: 'smooth'})"
                ),
            ).props("flat no-caps").classes("text-slate-400")

    market_host = ui.column().classes("w-full mt-10")
    representative_host = ui.column().classes("w-full mt-10")
    macro_host = ui.column().classes("w-full mt-10")
    news_host = ui.column().classes("w-full mt-10")

    await ui.context.client.connected()

    with market_host:
        ui.label("시장 한눈에 보기").classes("section-title")
        ui.label("주요 지수·환율·변동성").classes(
            "text-xs text-slate-500 mb-3"
        )
        market_grid = ui.grid(columns=7).classes(
            "w-full gap-2 max-xl:grid-cols-4 max-md:grid-cols-2"
        )

    async def load_market():
        data = await asyncio.to_thread(get_market_overview)
        market_grid.clear()
        with market_grid:
            for item in data:
                pct = item.get("percent")
                color = (
                    "text-red-400" if pct is not None and pct > 0
                    else "text-blue-400" if pct is not None and pct < 0
                    else "text-slate-400"
                )
                val = item.get("value")
                if val is None:
                    text = "-"
                elif item["symbol"] == "KRW=X":
                    text = f"{val:,.1f}원"
                elif item.get("suffix") == "%":
                    text = f"{val:.2f}%"
                else:
                    text = f"{val:,.2f}"
                with ui.card().classes("glass p-4"):
                    ui.label(item["name"]).classes(
                        "text-xs font-bold text-slate-500"
                    )
                    ui.label(text).classes("text-lg font-black text-white")
                    ui.label(
                        "-" if pct is None else f"{pct:+.2f}%"
                    ).classes(f"text-xs font-bold {color}")

    await load_market()
    ui.timer(60, load_market)

    with representative_host:
        with ui.row().classes("w-full items-end justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("오늘의 대표 종목").classes("section-title")
                ui.label(
                    "시가총액 대표 또는 대표 universe 내 최신 거래량 기준"
                ).classes("text-xs text-slate-500")
        market_toggle = ui.toggle(
            {"KR": "한국장", "US": "미국장"},
            value="KR",
        ).props("unelevated").classes("mt-4")
        mode_toggle = ui.toggle(
            {"cap": "시가총액 대표", "volume": "거래 활발"},
            value="cap",
        ).props("unelevated").classes("mt-2")
        stock_grid = ui.grid(columns=3).classes(
            "w-full gap-3 mt-4 max-lg:grid-cols-2 max-md:grid-cols-1"
        )

    async def load_representatives():
        stock_grid.clear()
        with stock_grid:
            ui.spinner(size="md").classes("m-8")
        data = await asyncio.to_thread(
            get_representative_stocks,
            market_toggle.value,
            mode_toggle.value,
            6,
        )
        stock_grid.clear()
        with stock_grid:
            for item in data:
                pct = item.get("percent")
                color = (
                    "text-red-400" if pct is not None and pct > 0
                    else "text-blue-400" if pct is not None and pct < 0
                    else "text-slate-400"
                )
                with ui.card().classes(
                    "glass stock-card p-5 min-h-[210px]"
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
                                "font-bold text-white text-lg"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']}"
                            ).classes("text-xs text-slate-500")
                        ui.label(item["market"]).classes(
                            "pill text-[10px] font-bold"
                        )
                    ui.label(fmt_public_price(item)).classes(
                        "text-2xl font-black text-white mt-3"
                    )
                    ui.label(
                        "-" if pct is None else f"{pct:+.2f}%"
                    ).classes(f"text-sm font-bold {color}")
                    svg = sparkline_svg(item.get("spark") or [])
                    if svg:
                        ui.html(svg).classes("w-full mt-3")

                    ui.label(
                        "클릭해서 상세 차트 보기"
                    ).classes("text-[11px] text-slate-600 mt-2")

    market_toggle.on(
        "update:model-value",
        lambda _: load_representatives(),
        throttle=0.2,
        leading_events=False,
        trailing_events=True,
    )
    mode_toggle.on(
        "update:model-value",
        lambda _: load_representatives(),
        throttle=0.2,
        leading_events=False,
        trailing_events=True,
    )
    await load_representatives()

    with macro_host:
        ui.label("주요 경제지표").classes("section-title")
        ui.label("FRED 기반 주요 미국 거시지표").classes(
            "text-xs text-slate-500 mb-3"
        )
        macro_grid = ui.grid(columns=4).classes(
            "w-full gap-3 max-md:grid-cols-2"
        )

    async def load_macro():
        data = await asyncio.to_thread(get_macro_overview)
        macro_grid.clear()
        with macro_grid:
            for item in data:
                value = item.get("value")
                change = item.get("change")
                color = (
                    "text-red-400" if change is not None and change > 0
                    else "text-blue-400" if change is not None and change < 0
                    else "text-slate-400"
                )
                with ui.card().classes("glass p-5"):
                    ui.label(item["name"]).classes(
                        "text-xs font-bold text-slate-500"
                    )
                    ui.label(
                        "-" if value is None
                        else f"{value:.2f}{item['suffix']}"
                    ).classes("text-xl font-black text-white mt-1")
                    ui.label(
                        "-" if change is None
                        else f"직전 대비 {change:+.2f}"
                    ).classes(f"text-xs {color}")

    await load_macro()

    # 공개 홈 뉴스는 대표적인 시장 ETF/종목을 가상의 watchlist 형태로 사용
    public_news_seed = [
        {"symbol": "005930", "name": "삼성전자", "market": "KR", "exchange": "KOSPI"},
        {"symbol": "000660", "name": "SK하이닉스", "market": "KR", "exchange": "KOSPI"},
        {"symbol": "NVDA", "name": "NVIDIA", "market": "US", "exchange": "NASDAQ"},
        {"symbol": "AAPL", "name": "Apple", "market": "US", "exchange": "NASDAQ"},
        {"symbol": "MSFT", "name": "Microsoft", "market": "US", "exchange": "NASDAQ"},
    ]

    with news_host:
        ui.label("시장 뉴스").classes("section-title")
        ui.label(
            "한국·미국 대표 종목 관련 최신 기사"
        ).classes("text-xs text-slate-500 mb-3")
        news_list = ui.column().classes(
            "w-full glass px-5"
        )

    async def load_public_news():
        data = await asyncio.to_thread(
            get_watchlist_news, public_news_seed, 10
        )
        news_list.clear()
        with news_list:
            if not data:
                ui.label("현재 표시할 뉴스가 없습니다.").classes(
                    "py-5 text-slate-500"
                )
            for item in data:
                with ui.row().classes(
                    "w-full py-4 border-b border-slate-800 "
                    "last:border-0 items-start justify-between gap-4"
                ):
                    with ui.column().classes("gap-1 min-w-0"):
                        if item.get("url"):
                            ui.link(
                                item["title"], item["url"], new_tab=True
                            ).classes(
                                "text-white font-semibold no-underline "
                                "hover:text-blue-400"
                            )
                        else:
                            ui.label(item["title"]).classes(
                                "text-white font-semibold"
                            )
                        ui.label(
                            " · ".join(
                                x for x in [
                                    item.get("symbol", ""),
                                    item.get("publisher", ""),
                                ] if x
                            )
                        ).classes("text-xs text-slate-500")

    await load_public_news()
    ui.timer(300, load_public_news)

    with ui.column().classes(
        "w-full glass p-7 mt-10 items-center text-center"
    ):
        ui.label("관심종목을 직접 구성하고 싶다면").classes(
            "text-xl font-black text-white"
        )
        ui.label(
            "로그인 후 종목을 저장하면 기기와 재배포에 관계없이 내 목록이 유지됩니다."
        ).classes("text-slate-400")
        ui.button(
            "내 대시보드 열기" if logged_in() else "로그인하고 시작하기",
            icon="arrow_forward",
            on_click=lambda: ui.navigate.to(
                "/dashboard" if logged_in() else "/login"
            ),
        ).props("unelevated no-caps").classes("primary mt-3 px-6")


@ui.page("/login")
def login_page():
    add_style()
    if logged_in():
        ui.navigate.to("/dashboard")
        return

    with ui.row().classes(
        "w-full items-center justify-between mb-10"
    ):
        ui.button(
            "시장 홈",
            icon="arrow_back",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat no-caps").classes("text-slate-400")
        ui.label("MY MARKET").classes(
            "text-sm font-black text-white"
        )

    with ui.column().classes(
        "w-full max-w-lg mx-auto mt-10"
    ):
        ui.label("로그인").classes(
            "text-4xl font-black text-white"
        )
        ui.label(
            "관심종목과 개인화 데이터를 저장하고 어디서든 다시 확인하세요."
        ).classes("text-slate-500 mt-1 mb-8")

        with ui.column().classes("w-full gap-2"):
            if ENABLE_KAKAO:
                ui.button(
                    "카카오로 계속하기",
                    icon="chat_bubble",
                    on_click=lambda: social_login("kakao"),
                ).props("unelevated no-caps").classes(
                    "w-full social social-kakao"
                )
            if ENABLE_GOOGLE:
                ui.button(
                    "Google로 계속하기",
                    icon="login",
                    on_click=lambda: social_login("google"),
                ).props("unelevated no-caps").classes(
                    "w-full social social-google"
                )
            if ENABLE_NAVER:
                ui.button(
                    "네이버로 계속하기",
                    icon="account_circle",
                    on_click=lambda: social_login("custom:naver"),
                ).props("unelevated no-caps").classes(
                    "w-full social social-naver"
                )
            if ENABLE_APPLE:
                ui.button(
                    "Apple로 계속하기",
                    icon="apple",
                    on_click=lambda: social_login("apple"),
                ).props("unelevated no-caps").classes(
                    "w-full social social-apple"
                )

        with ui.row().classes("w-full items-center gap-3 my-6"):
            ui.separator().classes("flex-1 bg-slate-800")
            ui.label("또는").classes("text-xs text-slate-600")
            ui.separator().classes("flex-1 bg-slate-800")

        email = ui.input(
            "이메일", placeholder="name@example.com"
        ).props("outlined dark").classes("w-full auth-input")
        password = ui.input(
            "비밀번호",
            password=True,
            password_toggle_button=True,
        ).props("outlined dark").classes("w-full auth-input")

        async def do_login():
            try:
                result = await asyncio.to_thread(
                    sign_in, email.value.strip(), password.value
                )
                save_auth_result(result)
                ui.navigate.to("/dashboard")
            except Exception as exc:
                ui.notify(f"로그인 실패: {exc}", type="negative")

        ui.button(
            "이메일로 로그인",
            on_click=do_login,
        ).props("unelevated no-caps").classes(
            "w-full primary h-12 mt-2 font-bold"
        )

        with ui.row().classes(
            "w-full justify-center gap-2 mt-6"
        ):
            ui.label("처음 방문하셨나요?").classes(
                "text-slate-600"
            )
            ui.link("회원가입", "/signup").classes(
                "text-blue-400 font-bold no-underline"
            )


@ui.page("/signup")
def signup_page():
    add_style()
    with ui.row().classes("w-full"):
        ui.button(
            "로그인으로",
            icon="arrow_back",
            on_click=lambda: ui.navigate.to("/login"),
        ).props("flat no-caps").classes("text-slate-400")

    with ui.column().classes("w-full max-w-lg mx-auto mt-12"):
        ui.label("회원가입").classes(
            "text-4xl font-black text-white"
        )
        ui.label("개인 대시보드를 위한 계정을 만듭니다.").classes(
            "text-slate-500 mb-7"
        )
        name = ui.input("표시 이름").props(
            "outlined dark"
        ).classes("w-full auth-input")
        email = ui.input("이메일").props(
            "outlined dark"
        ).classes("w-full auth-input")
        pw = ui.input(
            "비밀번호", password=True,
            password_toggle_button=True,
        ).props("outlined dark").classes("w-full auth-input")
        confirm = ui.input(
            "비밀번호 확인", password=True,
            password_toggle_button=True,
        ).props("outlined dark").classes("w-full auth-input")

        async def do_signup():
            if pw.value != confirm.value:
                ui.notify("비밀번호가 서로 다릅니다.", type="warning")
                return
            try:
                result = await asyncio.to_thread(
                    sign_up,
                    email.value.strip(),
                    pw.value,
                    (name.value or "").strip(),
                )
                if result.session:
                    save_auth_result(result)
                    ui.navigate.to("/dashboard")
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
            "회원가입",
            on_click=do_signup,
        ).props("unelevated no-caps").classes(
            "w-full primary h-12 mt-2 font-bold"
        )


@ui.page("/oauth/callback")
def oauth_callback():
    add_style()
    with ui.column().classes(
        "w-full min-h-[75vh] items-center justify-center"
    ):
        ui.spinner(size="lg")
        ui.label("로그인을 완료하고 있습니다...").classes(
            "text-slate-400 mt-4"
        )

    async def finalize():
        try:
            hash_value = await ui.run_javascript(
                "window.location.hash || ''"
            )
            params = parse_qs(str(hash_value).lstrip("#"))
            access = params.get("access_token", [None])[0]
            refresh = params.get("refresh_token", [None])[0]
            if access and refresh:
                app.storage.user["access_token"] = access
                app.storage.user["refresh_token"] = refresh
                ui.navigate.to("/dashboard")
                return

            error = params.get(
                "error_description", params.get("error", [None])
            )[0]
            ui.notify(
                f"소셜 로그인 실패: {error or '토큰을 받지 못했습니다.'}",
                type="negative",
                timeout=8000,
            )
            ui.navigate.to("/login")
        except Exception as exc:
            ui.notify(f"OAuth 처리 실패: {exc}", type="negative")
            ui.navigate.to("/login")

    ui.timer(0.5, finalize, once=True)


@ui.page("/dashboard", response_timeout=15)
async def personal_dashboard():
    add_style()
    if not require_login():
        return

    with ui.row().classes("w-full items-center justify-between"):
        ui.button(
            "시장 홈",
            icon="public",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat no-caps").classes("text-slate-400")
        account_area = ui.row().classes("items-center gap-2")

    with ui.column().classes("gap-0 mt-5"):
        ui.label("PERSONAL DASHBOARD").classes(
            "text-[11px] tracking-[.18em] font-bold text-slate-500"
        )
        title = ui.label("MY MARKET").classes(
            "text-4xl font-black text-white"
        )

    stats = ui.grid(columns=3).classes(
        "w-full gap-3 mt-7 max-md:grid-cols-1"
    )
    search_host = ui.column().classes("w-full mt-9")
    watch_host = ui.column().classes("w-full mt-9")
    macro_host = ui.column().classes("w-full mt-10")
    news_host = ui.column().classes("w-full mt-10")

    await ui.context.client.connected()

    try:
        user = await asyncio.to_thread(get_user, app.storage.user)
        profile = await asyncio.to_thread(get_profile, app.storage.user)
        watchlist = await asyncio.to_thread(
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
        ui.navigate.to("/")

    with account_area:
        ui.label(display_name).classes(
            "text-sm font-bold text-slate-300"
        )
        with ui.button(icon="account_circle").props("flat round"):
            with ui.menu():
                ui.menu_item("시장 홈", lambda: ui.navigate.to("/"))
                ui.menu_item("로그아웃", logout)

    with stats:
        with ui.card().classes("glass p-5"):
            ui.label("ACCOUNT").classes(
                "text-xs font-bold text-slate-500"
            )
            ui.label(display_name).classes(
                "text-xl font-black text-white mt-2"
            )
            ui.label("Supabase Auth").classes(
                "text-xs text-slate-500"
            )
        with ui.card().classes("glass p-5"):
            ui.label("KIS").classes(
                "text-xs font-bold text-slate-500"
            )
            ui.label(
                "CONNECTED" if kis.enabled() else "NOT CONFIGURED"
            ).classes("text-xl font-black text-white mt-2")
            ui.label("한국주식 시세").classes(
                "text-xs text-slate-500"
            )
        with ui.card().classes("glass p-5"):
            ui.label("WATCHLIST").classes(
                "text-xs font-bold text-slate-500"
            )
            watch_count = ui.label(str(len(watchlist))).classes(
                "text-xl font-black text-white mt-2"
            )
            ui.label("내 관심종목").classes(
                "text-xs text-slate-500"
            )

    with search_host:
        ui.label("종목 검색").classes("section-title")
        search = ui.input(
            placeholder="삼성, 005930, NVDA, NVIDIA, AAPL"
        ).props("outlined dark clearable").classes(
            "w-full search-box mt-2"
        )
        results = ui.column().classes("w-full gap-2 mt-2")

    with watch_host:
        ui.label("내 관심종목").classes("section-title")
        watch_grid = ui.grid(columns=3).classes(
            "w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1"
        )

    quote_refs = {}

    async def refresh_quotes():
        for refs in list(quote_refs.values()):
            item = refs["item"]
            try:
                if item["market"] == "KR":
                    q = await asyncio.to_thread(
                        kis.get_domestic_quote, item["symbol"]
                    )
                else:
                    q = await asyncio.to_thread(
                        get_us_quote, item["symbol"]
                    )
                price, chg, pct = q.get("price"), q.get("change"), q.get("change_percent")
                if q.get("currency") == "KRW":
                    refs["price"].set_text(
                        "-" if price is None else f"{price:,.0f}원"
                    )
                    refs["change"].set_text(
                        "-" if chg is None or pct is None
                        else f"{chg:+,.0f}원 ({pct:+.2f}%)"
                    )
                else:
                    refs["price"].set_text(
                        "-" if price is None else f"${price:,.2f}"
                    )
                    refs["change"].set_text(
                        "-" if chg is None or pct is None
                        else f"${chg:+,.2f} ({pct:+.2f}%)"
                    )
            except Exception:
                refs["price"].set_text("조회 실패")

    async def render_watchlist():
        watch_grid.clear()
        quote_refs.clear()
        watch_count.set_text(str(len(watchlist)))
        with watch_grid:
            if not watchlist:
                with ui.card().classes("glass p-7"):
                    ui.label("아직 저장한 관심종목이 없습니다.").classes(
                        "text-white font-bold"
                    )
                    ui.label(
                        "위 검색창에서 종목을 추가하거나 시장 홈에서 종목을 살펴보세요."
                    ).classes("text-sm text-slate-500")
                return

            for item in watchlist:
                key = f"{item['market']}:{item['exchange']}:{item['symbol']}"
                with ui.card().classes(
                    "glass stock-card p-5 min-h-[300px]"
                ) as card:
                    card.on(
                        "click",
                        lambda _, x=item: ui.navigate.to(
                            f"/stock/{x['market']}/"
                            f"{quote(x['exchange'], safe='')}/"
                            f"{quote(x['symbol'], safe='')}"
                        ),
                    )
                    ui.label(item["name"]).classes(
                        "text-lg font-bold text-white"
                    )
                    ui.label(
                        f"{item['symbol']} · {item['exchange']}"
                    ).classes("text-xs text-slate-500")
                    price = ui.label("불러오는 중...").classes(
                        "text-2xl font-black text-white mt-4"
                    )
                    change = ui.label("-").classes(
                        "text-sm font-bold text-slate-400"
                    )
                    spark_host = ui.column().classes(
                        "w-full h-[82px] mt-3"
                    )

                    async def remove(event, current=item):
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
                        watchlist[:] = [
                            x for x in watchlist
                            if not (
                                x["market"] == current["market"]
                                and x["exchange"] == current["exchange"]
                                and x["symbol"] == current["symbol"]
                            )
                        ]
                        await render_watchlist()
                        await load_news()

                    ui.button(
                        "삭제",
                        on_click=remove,
                    ).props("flat dense").classes(
                        "w-full mt-3 text-slate-500"
                    )

                    quote_refs[key] = {
                        "item": item,
                        "price": price,
                        "change": change,
                        "spark": spark_host,
                    }

        async def spark_one(refs):
            i = refs["item"]
            svg = await asyncio.to_thread(
                get_sparkline_svg,
                i["market"], i["exchange"], i["symbol"],
            )
            refs["spark"].clear()
            with refs["spark"]:
                if svg:
                    ui.html(svg).classes("w-full")
        await asyncio.gather(
            refresh_quotes(),
            *(spark_one(r) for r in quote_refs.values()),
        )

    async def do_search():
        q = (search.value or "").strip()
        results.clear()
        if not q:
            return
        found = await asyncio.to_thread(search_stocks, q)
        with results:
            for item in found[:8]:
                with ui.card().classes("w-full glass px-4 py-3"):
                    with ui.row().classes(
                        "w-full items-center justify-between"
                    ):
                        with ui.column().classes("gap-0"):
                            ui.label(item["name"]).classes(
                                "text-white font-bold"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']} · {item['market']}"
                            ).classes("text-xs text-slate-500")

                        async def add(current=item):
                            saved = await asyncio.to_thread(
                                add_watchlist,
                                app.storage.user,
                                current,
                            )
                            exists = any(
                                x["market"] == current["market"]
                                and x["exchange"] == current["exchange"]
                                and x["symbol"] == current["symbol"]
                                for x in watchlist
                            )
                            if not exists:
                                watchlist.append(saved or current)
                            search.set_value("")
                            results.clear()
                            await render_watchlist()
                            await load_news()

                        ui.button(
                            "추가", icon="add", on_click=add
                        ).props("unelevated").classes("primary")

    search.on(
        "update:model-value",
        lambda _: do_search(),
        throttle=0.35,
        leading_events=False,
        trailing_events=True,
    )

    await render_watchlist()
    ui.timer(REFRESH_SECONDS, refresh_quotes)

    with macro_host:
        ui.label("주요 경제지표").classes("section-title")
        macro_grid = ui.grid(columns=4).classes(
            "w-full gap-3 mt-3 max-md:grid-cols-2"
        )

    data = await asyncio.to_thread(get_macro_overview)
    with macro_grid:
        for item in data:
            with ui.card().classes("glass p-4"):
                ui.label(item["name"]).classes(
                    "text-xs text-slate-500 font-bold"
                )
                ui.label(
                    "-" if item["value"] is None
                    else f"{item['value']:.2f}{item['suffix']}"
                ).classes("text-xl font-black text-white")

    with news_host:
        ui.label("내 관심종목 뉴스").classes("section-title")
        news_list = ui.column().classes(
            "w-full glass px-5 mt-3"
        )

    async def load_news():
        data = await asyncio.to_thread(
            get_watchlist_news, watchlist, 10
        )
        news_list.clear()
        with news_list:
            if not data:
                ui.label("표시할 뉴스가 없습니다.").classes(
                    "py-5 text-slate-500"
                )
            for item in data:
                with ui.column().classes(
                    "w-full py-4 border-b border-slate-800 last:border-0 gap-1"
                ):
                    if item.get("url"):
                        ui.link(
                            item["title"], item["url"], new_tab=True
                        ).classes(
                            "text-white font-semibold no-underline hover:text-blue-400"
                        )
                    else:
                        ui.label(item["title"]).classes(
                            "text-white font-semibold"
                        )
                    ui.label(
                        " · ".join(
                            x for x in [
                                item.get("symbol", ""),
                                item.get("publisher", ""),
                            ] if x
                        )
                    ).classes("text-xs text-slate-500")

    await load_news()


@ui.page(
    "/stock/{market}/{exchange}/{symbol}",
    response_timeout=15,
)
async def stock_detail(market: str, exchange: str, symbol: str):
    add_style()

    with ui.row().classes(
        "w-full items-center justify-between sticky top-0 z-10 "
        "bg-[#07090d]/95 py-3"
    ):
        ui.button(
            "이전 화면",
            icon="arrow_back",
            on_click=lambda: ui.run_javascript("history.back()"),
        ).props("flat no-caps").classes("text-blue-400 font-bold")
        with ui.row().classes("gap-2"):
            ui.button(
                "시장 홈",
                icon="public",
                on_click=lambda: ui.navigate.to("/"),
            ).props("flat no-caps").classes("text-slate-400")
            if logged_in():
                ui.button(
                    "내 대시보드",
                    icon="dashboard",
                    on_click=lambda: ui.navigate.to("/dashboard"),
                ).props("flat no-caps").classes("text-slate-400")

    with ui.column().classes("gap-0 mt-5"):
        name_label = ui.label(symbol).classes(
            "text-3xl font-black text-white"
        )
        ui.label(
            f"{symbol} · {exchange} · {market}"
        ).classes("text-sm text-slate-500")

    with ui.card().classes("glass p-5 mt-5"):
        price_label = ui.label("가격 불러오는 중...").classes(
            "text-3xl font-black text-white"
        )
        change_label = ui.label("-").classes(
            "text-sm font-bold text-slate-400"
        )

    if logged_in():
        action_host = ui.row().classes("mt-3")
    else:
        with ui.row().classes("mt-3 items-center gap-2"):
            ui.label(
                "관심종목 저장은 로그인 후 사용할 수 있습니다."
            ).classes("text-xs text-slate-600")
            ui.button(
                "로그인",
                on_click=lambda: ui.navigate.to("/login"),
            ).props("flat dense no-caps").classes("text-blue-400")

    ui.label("차트").classes("section-title mt-8")
    timeframe = ui.toggle(
        {"1D":"1일","D":"일봉","W":"주봉","M":"월봉"},
        value="D",
    ).props("unelevated").classes("mt-3")
    ma = ui.select(
        options={5:"MA5",20:"MA20",60:"MA60",120:"MA120"},
        value=[5,20,60,120],
        multiple=True,
        label="이동평균선",
    ).props("outlined dark use-chips").classes(
        "w-full max-w-xl mt-3"
    )
    chart_host = ui.column().classes(
        "w-full chart-wrap min-h-[560px] mt-4"
    )
    with chart_host:
        ui.spinner(size="lg").classes("m-auto mt-24")

    await ui.context.client.connected()

    # Try to resolve a friendlier name from personal watchlist or search.
    current_item = {
        "symbol": symbol,
        "name": symbol,
        "market": market,
        "exchange": exchange,
    }
    if logged_in():
        try:
            await asyncio.to_thread(get_user, app.storage.user)
            personal = await asyncio.to_thread(
                load_watchlist, app.storage.user
            )
            found = next(
                (
                    x for x in personal
                    if x["market"] == market
                    and x["exchange"] == exchange
                    and x["symbol"] == symbol
                ),
                None,
            )
            if found:
                current_item = found
                name_label.set_text(found["name"])
        except Exception:
            pass

    if current_item["name"] == symbol:
        try:
            search_result = await asyncio.to_thread(
                search_stocks, symbol
            )
            found = next(
                (
                    x for x in search_result
                    if x["market"] == market
                    and x["symbol"] == symbol
                ),
                None,
            )
            if found:
                current_item = found
                name_label.set_text(found["name"])
        except Exception:
            pass

    if logged_in():
        with action_host:
            async def save_to_watchlist():
                try:
                    await asyncio.to_thread(
                        add_watchlist,
                        app.storage.user,
                        current_item,
                    )
                    ui.notify(
                        f"{current_item['name']} 관심종목에 저장했습니다.",
                        type="positive",
                    )
                except Exception as exc:
                    ui.notify(f"저장 실패: {exc}", type="negative")

            ui.button(
                "관심종목에 저장",
                icon="star",
                on_click=save_to_watchlist,
            ).props("outline no-caps").classes("text-blue-400")

    async def header_quote():
        try:
            q = (
                await asyncio.to_thread(
                    kis.get_domestic_quote, symbol
                )
                if market == "KR"
                else await asyncio.to_thread(get_us_quote, symbol)
            )
            p, c, pct = q.get("price"), q.get("change"), q.get("change_percent")
            if q.get("currency") == "KRW":
                price_label.set_text(
                    "-" if p is None else f"{p:,.0f}원"
                )
                change_label.set_text(
                    "-" if c is None or pct is None
                    else f"{c:+,.0f}원 ({pct:+.2f}%)"
                )
            else:
                price_label.set_text(
                    "-" if p is None else f"${p:,.2f}"
                )
                change_label.set_text(
                    "-" if c is None or pct is None
                    else f"${c:+,.2f} ({pct:+.2f}%)"
                )
        except Exception as exc:
            price_label.set_text("조회 실패")
            change_label.set_text(str(exc)[:90])

    lock = asyncio.Lock()

    async def render_chart():
        if lock.locked():
            return
        async with lock:
            chart_host.clear()
            with chart_host:
                ui.spinner(size="lg").classes("m-auto mt-24")
            try:
                fig = await asyncio.to_thread(
                    get_chart_figure,
                    kis,
                    market,
                    exchange,
                    symbol,
                    timeframe.value,
                    tuple(ma.value or []),
                )
                chart_host.clear()
                with chart_host:
                    ui.plotly(fig).classes("w-full h-[620px]")
            except Exception as exc:
                chart_host.clear()
                with chart_host:
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
    ma.on(
        "update:model-value",
        lambda _: render_chart(),
        throttle=0.2,
        leading_events=False,
        trailing_events=True,
    )

    await asyncio.gather(header_quote(), render_chart())


@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now().isoformat()}


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
