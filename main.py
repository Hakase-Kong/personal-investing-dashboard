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
    get_watchlist_news,
)
from kis import KISClient
from market_data import get_us_quote, search_stocks
from public_data import get_representative_stocks
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

PORT = int(os.getenv("PORT", "8080"))
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "5"))
STORAGE_SECRET = os.getenv("STORAGE_SECRET", "change-this-in-render")
APP_URL = os.getenv("APP_URL", "").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")

ENABLE_GOOGLE = os.getenv("ENABLE_GOOGLE", "true").lower() == "true"
ENABLE_KAKAO = os.getenv("ENABLE_KAKAO", "true").lower() == "true"
ENABLE_NAVER = os.getenv("ENABLE_NAVER", "true").lower() == "true"
ENABLE_APPLE = os.getenv("ENABLE_APPLE", "false").lower() == "true"

kis = KISClient(
    os.getenv("KIS_APP_KEY", ""),
    os.getenv("KIS_APP_SECRET", ""),
    os.getenv("KIS_ENV", "real"),
)


def add_style():
    ui.add_head_html(
        """
        <meta name="color-scheme" content="light dark">
        <style>
            :root {
                --page:#f4f7fb;
                --surface:#ffffff;
                --surface-2:#f8fafc;
                --border:#dbe3ed;
                --text:#0f172a;
                --muted:#64748b;
                --soft:#94a3b8;
                --blue:#2563eb;
                --blue-soft:#eff6ff;
                --hero-a:#f8fbff;
                --hero-b:#edf6ff;
                --shadow:0 8px 30px rgba(15,23,42,.06);
                --red:#dc2626;
                --down:#2563eb;
            }
            body.body--dark {
                --page:#07090d;
                --surface:#0f141c;
                --surface-2:#0c1118;
                --border:#263244;
                --text:#f8fafc;
                --muted:#8292aa;
                --soft:#53637c;
                --blue:#5da9e9;
                --blue-soft:#0d1d32;
                --hero-a:#0c1321;
                --hero-b:#081c2b;
                --shadow:none;
                --red:#ff4d57;
                --down:#4594ff;
            }
            html, body { background:var(--page)!important; }
            body { color:var(--text); transition:background .18s ease,color .18s ease; }
            .nicegui-content {
                max-width:1240px;
                margin:0 auto;
                padding:24px 24px 72px;
            }
            .surface {
                background:var(--surface)!important;
                border:1px solid var(--border)!important;
                border-radius:18px!important;
                box-shadow:var(--shadow)!important;
                color:var(--text)!important;
            }
            .hero {
                background:linear-gradient(135deg,var(--hero-a),var(--hero-b));
                border:1px solid var(--border);
                border-radius:24px;
                color:var(--text);
            }
            .muted { color:var(--muted)!important; }
            .soft { color:var(--soft)!important; }
            .main-text { color:var(--text)!important; }
            .stock-card,.market-card {
                cursor:pointer;
                transition:transform .15s ease,border-color .15s ease;
            }
            .stock-card:hover,.market-card:hover {
                transform:translateY(-2px);
                border-color:color-mix(in srgb,var(--blue) 60%,var(--border))!important;
            }
            .pill {
                background:var(--surface-2);
                border:1px solid var(--border);
                border-radius:999px;
                padding:6px 11px;
                color:var(--muted);
            }
            .filter-shell {
                display:flex;
                flex-wrap:wrap;
                gap:8px;
                padding:7px;
                width:max-content;
                max-width:100%;
                background:var(--surface);
                border:1px solid var(--border);
                border-radius:14px;
                box-shadow:var(--shadow);
            }
            .q-btn.filter-button {
                border-radius:9px!important;
                min-height:34px!important;
                padding:0 14px!important;
                color:var(--muted)!important;
            }
            .q-btn.filter-active {
                background:var(--blue)!important;
                color:white!important;
            }
            .search-box .q-field__control,.auth-input .q-field__control {
                background:var(--surface)!important;
                border-radius:14px!important;
                color:var(--text)!important;
            }
            .search-box .q-field__native,.auth-input .q-field__native {
                color:var(--text)!important;
            }
            .primary { background:var(--blue)!important; color:white!important; border-radius:11px!important; }
            .live-dot {
                width:8px;height:8px;border-radius:999px;background:#4ade80;
                box-shadow:0 0 12px rgba(74,222,128,.55);
            }
            .section-title { font-size:1.15rem;font-weight:800;color:var(--text); }
            .positive { color:var(--red)!important; }
            .negative { color:var(--down)!important; }
            .chart-wrap {
                background:var(--surface);
                border:1px solid var(--border);
                border-radius:18px;
                overflow:hidden;
            }
            .loading-shimmer {
                position:relative;
                overflow:hidden;
                background:var(--surface);
            }
            .loading-shimmer:after {
                content:"";
                position:absolute;
                inset:0;
                transform:translateX(-100%);
                background:linear-gradient(90deg,transparent,rgba(148,163,184,.12),transparent);
                animation:shimmer 1.4s infinite;
            }
            @keyframes shimmer { 100% { transform:translateX(100%); } }
            .social { border-radius:12px!important;min-height:48px;font-weight:700!important; }
            .social-google { background:#1b2028!important;color:#fff!important;border:1px solid #343b48!important; }
            .social-kakao { background:#fee500!important;color:#171717!important; }
            .social-naver { background:#03c75a!important;color:#fff!important; }
            .social-apple { background:#f5f5f7!important;color:#0b0b0c!important; }
        </style>
        """
    )


def apply_theme():
    pref = app.storage.user.get("theme_pref", "system")
    dark = ui.dark_mode(
        value=None if pref == "system" else pref == "dark"
    )

    async def set_theme(value):
        app.storage.user["theme_pref"] = value
        if value == "system":
            dark.auto()
        elif value == "dark":
            dark.enable()
        else:
            dark.disable()

    return dark, set_theme


def logged_in():
    return bool(
        app.storage.user.get("access_token")
        and app.storage.user.get("refresh_token")
    )


def clear_session():
    for key in [
        "access_token", "refresh_token", "user_id",
        "email", "display_name",
    ]:
        app.storage.user.pop(key, None)


def save_auth_result(result):
    if result.session:
        app.storage.user["access_token"] = result.session.access_token
        app.storage.user["refresh_token"] = result.session.refresh_token
    if result.user:
        app.storage.user["user_id"] = str(result.user.id)
        app.storage.user["email"] = result.user.email or ""


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


def theme_menu(set_theme):
    with ui.button(icon="contrast").props("flat round dense"):
        with ui.menu():
            ui.menu_item(
                "시스템 설정",
                lambda: set_theme("system"),
            )
            ui.menu_item(
                "라이트 모드",
                lambda: set_theme("light"),
            )
            ui.menu_item(
                "다크 모드",
                lambda: set_theme("dark"),
            )


def public_header(set_theme):
    with ui.row().classes("w-full items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.label("MY MARKET").classes(
                "text-2xl font-black tracking-tight main-text"
            )
            ui.label("PUBLIC").classes("pill text-[10px] font-bold")

        with ui.row().classes("items-center gap-3"):
            kst = ui.label("--:-- KST").classes(
                "text-sm font-bold main-text tabular-nums"
            )
            theme_menu(set_theme)

            if logged_in():
                ui.button(
                    "내 대시보드",
                    icon="dashboard",
                    on_click=lambda: ui.navigate.to("/dashboard"),
                ).props("flat no-caps").classes("font-bold")
            else:
                ui.button(
                    "로그인",
                    icon="login",
                    on_click=lambda: ui.navigate.to("/login"),
                ).props("outline no-caps")

    def tick():
        kst.set_text(
            datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S KST")
        )
    tick()
    ui.timer(1.0, tick)


def delta_class(value):
    if value is None or value == 0:
        return "muted"
    return "positive" if value > 0 else "negative"


def market_value_text(item):
    value = item.get("value")
    if value is None:
        return "-"
    if item["symbol"] == "KRW=X":
        return f"{value:,.1f}원"
    if item.get("suffix") == "%":
        return f"{value:.2f}%"
    return f"{value:,.2f}"


def stock_price_text(item):
    value = item.get("price")
    if value is None:
        return "-"
    if item["market"] == "KR":
        return f"{value:,.0f}원"
    return f"${value:,.2f}"


def mini_svg(values, width=260, height=52):
    if not values or len(values) < 2:
        return ""
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 2:
        return ""

    lo, hi = min(vals), max(vals)
    span = max(hi - lo, 1e-9)
    px, py = 3, 5
    points = []
    for i, v in enumerate(vals):
        x = px + (width - px * 2) * i / (len(vals) - 1)
        y = py + (height - py * 2) * (hi - v) / span
        points.append(f"{x:.1f},{y:.1f}")

    css = "var(--red)" if vals[-1] >= vals[0] else "var(--down)"
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'preserveAspectRatio="none">'
        f'<polyline points="{" ".join(points)}" fill="none" '
        f'stroke="{css}" stroke-width="2.1" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def search_component(target_route="/stock"):
    with ui.column().classes("w-full"):
        ui.label("종목 검색").classes("section-title")
        search = ui.input(
            placeholder="삼성, 005930, NVDA, NVIDIA, AAPL"
        ).props("outlined clearable").classes("w-full search-box mt-2")
        results = ui.column().classes("w-full gap-2 mt-1")

    generation = {"n": 0}

    async def do_search():
        generation["n"] += 1
        my_generation = generation["n"]
        q = (search.value or "").strip()
        results.clear()

        if not q:
            return

        found = await asyncio.to_thread(search_stocks, q)
        if my_generation != generation["n"]:
            return

        with results:
            for item in found[:8]:
                with ui.card().classes("w-full surface px-4 py-3"):
                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(item["name"]).classes(
                                "font-bold main-text"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']} · {item['market']}"
                            ).classes("text-xs muted")

                        ui.button(
                            "차트",
                            icon="show_chart",
                            on_click=lambda x=item: ui.navigate.to(
                                f"/stock/{x['market']}/"
                                f"{quote(x['exchange'], safe='')}/"
                                f"{quote(x['symbol'], safe='')}"
                            ),
                        ).props("flat dense no-caps")

    search.on(
        "update:model-value",
        lambda _: do_search(),
        throttle=0.28,
        leading_events=False,
        trailing_events=True,
    )
    return search, results


@ui.page("/", response_timeout=15)
async def public_home():
    add_style()
    _, set_theme = apply_theme()
    public_header(set_theme)

    with ui.column().classes("w-full hero p-7 mt-6 gap-2"):
        ui.label("시장을 보고, 로그인하면 내 투자 화면으로.").classes(
            "text-3xl md:text-4xl font-black main-text"
        )
        ui.label(
            "한국·미국 대표 종목, 주요 지수, 경제지표와 뉴스를 로그인 없이 확인하세요."
        ).classes("muted max-w-3xl")
        with ui.row().classes("gap-2 mt-4"):
            ui.button(
                "내 대시보드" if logged_in() else "개인화 시작하기",
                icon="dashboard" if logged_in() else "person",
                on_click=lambda: ui.navigate.to(
                    "/dashboard" if logged_in() else "/login"
                ),
            ).props("unelevated no-caps").classes("primary px-5")

    # Public search appears before remote market data.
    search_host = ui.column().classes("w-full mt-8")
    with search_host:
        search_component()

    market_host = ui.column().classes("w-full mt-9")
    stocks_host = ui.column().classes("w-full mt-10")
    macro_host = ui.column().classes("w-full mt-10")
    news_host = ui.column().classes("w-full mt-10")

    # Render all containers before network I/O.
    with market_host:
        ui.label("시장 한눈에 보기").classes("section-title")
        ui.label(
            "카드의 미니차트는 최근 거래일 흐름입니다."
        ).classes("text-xs muted mb-3")
        market_grid = ui.grid(columns=7).classes(
            "w-full gap-2 max-xl:grid-cols-4 max-md:grid-cols-2"
        )
        for _ in range(7):
            ui.card().classes(
                "surface loading-shimmer h-[145px]"
            )

    with stocks_host:
        ui.label("오늘의 대표 종목").classes("section-title")
        ui.label(
            "대표 대형주 또는 대표 universe 내 최신 거래량 기준"
        ).classes("text-xs muted mb-3")

        with ui.row().classes("filter-shell mt-2") as filter_bar:
            kr_btn = ui.button("한국장").props(
                "flat no-caps dense"
            ).classes("filter-button filter-active")
            us_btn = ui.button("미국장").props(
                "flat no-caps dense"
            ).classes("filter-button")
            ui.separator().props("vertical").classes("mx-1")
            cap_btn = ui.button(
                "시가총액 대표"
            ).props("flat no-caps dense").classes(
                "filter-button filter-active"
            )
            volume_btn = ui.button(
                "거래 활발"
            ).props("flat no-caps dense").classes("filter-button")

        stock_grid = ui.grid(columns=3).classes(
            "w-full gap-3 mt-4 max-lg:grid-cols-2 max-md:grid-cols-1"
        )
        for _ in range(6):
            ui.card().classes(
                "surface loading-shimmer h-[220px]"
            )

    with macro_host:
        ui.label("주요 경제지표").classes("section-title")
        macro_grid = ui.grid(columns=4).classes(
            "w-full gap-3 mt-3 max-md:grid-cols-2"
        )
        for _ in range(4):
            ui.card().classes(
                "surface loading-shimmer h-[105px]"
            )

    with news_host:
        ui.label("시장 뉴스").classes("section-title")
        news_list = ui.column().classes(
            "w-full surface px-5 mt-3 min-h-[150px]"
        )
        with news_list:
            ui.spinner(size="md").classes("m-auto mt-10")

    await ui.context.client.connected()

    state = {"market": "KR", "mode": "cap"}

    async def load_markets():
        data = await asyncio.to_thread(get_market_overview)
        market_grid.clear()
        with market_grid:
            for item in data:
                with ui.card().classes(
                    "surface market-card p-4 min-h-[145px]"
                ):
                    ui.label(item["name"]).classes(
                        "text-xs font-bold muted"
                    )
                    ui.label(market_value_text(item)).classes(
                        "text-lg font-black main-text"
                    )
                    pct = item.get("percent")
                    ui.label(
                        "-" if pct is None else f"{pct:+.2f}%"
                    ).classes(
                        f"text-xs font-bold {delta_class(pct)}"
                    )
                    svg = mini_svg(item.get("spark") or [], height=42)
                    if svg:
                        ui.html(svg).classes("w-full mt-2")

    def paint_filter_buttons():
        for button, active in [
            (kr_btn, state["market"] == "KR"),
            (us_btn, state["market"] == "US"),
            (cap_btn, state["mode"] == "cap"),
            (volume_btn, state["mode"] == "volume"),
        ]:
            button.classes(
                add="filter-active" if active else "",
                remove="" if active else "filter-active",
            )

    async def load_stocks():
        data = await asyncio.to_thread(
            get_representative_stocks,
            state["market"],
            state["mode"],
            6,
        )
        stock_grid.clear()
        with stock_grid:
            for item in data:
                with ui.card().classes(
                    "surface stock-card p-5 min-h-[220px]"
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
                                "font-bold main-text text-lg"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']}"
                            ).classes("text-xs muted")
                        ui.label(item["market"]).classes(
                            "pill text-[10px] font-bold"
                        )
                    ui.label(stock_price_text(item)).classes(
                        "text-2xl font-black main-text mt-3"
                    )
                    pct = item.get("percent")
                    ui.label(
                        "-" if pct is None else f"{pct:+.2f}%"
                    ).classes(
                        f"text-sm font-bold {delta_class(pct)}"
                    )
                    svg = mini_svg(item.get("spark") or [], height=58)
                    if svg:
                        ui.html(svg).classes("w-full mt-3")
                    ui.label("클릭해서 상세 차트").classes(
                        "text-[11px] soft mt-1"
                    )

    async def choose_market(value):
        state["market"] = value
        paint_filter_buttons()
        await load_stocks()

    async def choose_mode(value):
        state["mode"] = value
        paint_filter_buttons()
        await load_stocks()

    kr_btn.on_click(lambda: choose_market("KR"))
    us_btn.on_click(lambda: choose_market("US"))
    cap_btn.on_click(lambda: choose_mode("cap"))
    volume_btn.on_click(lambda: choose_mode("volume"))

    async def load_macro():
        data = await asyncio.to_thread(get_macro_overview)
        macro_grid.clear()
        with macro_grid:
            for item in data:
                with ui.card().classes("surface p-4"):
                    ui.label(item["name"]).classes(
                        "text-xs font-bold muted"
                    )
                    ui.label(
                        "-" if item["value"] is None
                        else f"{item['value']:.2f}{item['suffix']}"
                    ).classes("text-xl font-black main-text mt-1")
                    change = item.get("change")
                    ui.label(
                        "-" if change is None
                        else f"직전 대비 {change:+.2f}"
                    ).classes(
                        f"text-xs {delta_class(change)}"
                    )
                    svg = mini_svg(item.get("spark") or [], height=36)
                    if svg:
                        ui.html(svg).classes("w-full mt-2")

    news_seed = [
        {"symbol":"005930","name":"삼성전자","market":"KR","exchange":"KOSPI"},
        {"symbol":"000660","name":"SK하이닉스","market":"KR","exchange":"KOSPI"},
        {"symbol":"NVDA","name":"NVIDIA","market":"US","exchange":"NASDAQ"},
        {"symbol":"AAPL","name":"Apple","market":"US","exchange":"NASDAQ"},
    ]

    async def load_news():
        data = await asyncio.to_thread(
            get_watchlist_news, news_seed, 8
        )
        news_list.clear()
        with news_list:
            if not data:
                ui.label("현재 표시할 뉴스가 없습니다.").classes(
                    "py-5 muted"
                )
            for item in data:
                with ui.column().classes(
                    "w-full py-4 border-b border-[var(--border)] last:border-0 gap-1"
                ):
                    if item.get("url"):
                        ui.link(
                            item["title"],
                            item["url"],
                            new_tab=True,
                        ).classes(
                            "main-text font-semibold no-underline"
                        )
                    else:
                        ui.label(item["title"]).classes(
                            "main-text font-semibold"
                        )
                    ui.label(
                        " · ".join(
                            x for x in [
                                item.get("symbol", ""),
                                item.get("publisher", ""),
                            ] if x
                        )
                    ).classes("text-xs muted")

    # Major speed-up: independent feeds load in parallel.
    await asyncio.gather(
        load_markets(),
        load_stocks(),
        load_macro(),
        load_news(),
    )

    ui.timer(60, load_markets)
    ui.timer(300, load_news)


@ui.page("/login")
def login_page():
    add_style()
    _, set_theme = apply_theme()

    if logged_in():
        ui.navigate.to("/dashboard")
        return

    with ui.row().classes("w-full items-center justify-between"):
        ui.button(
            "시장 홈",
            icon="arrow_back",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat no-caps")
        theme_menu(set_theme)

    with ui.column().classes("w-full max-w-lg mx-auto mt-12"):
        ui.label("로그인").classes(
            "text-4xl font-black main-text"
        )
        ui.label(
            "관심종목과 개인화 데이터를 저장하고 어디서든 다시 확인하세요."
        ).classes("muted mt-1 mb-8")

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
            ui.separator().classes("flex-1")
            ui.label("또는").classes("text-xs muted")
            ui.separator().classes("flex-1")

        email = ui.input(
            "이메일",
            placeholder="name@example.com",
        ).props("outlined").classes("w-full auth-input")
        password = ui.input(
            "비밀번호",
            password=True,
            password_toggle_button=True,
        ).props("outlined").classes("w-full auth-input")

        async def do_login():
            try:
                result = await asyncio.to_thread(
                    sign_in,
                    email.value.strip(),
                    password.value,
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
            ui.label("처음 방문하셨나요?").classes("muted")
            ui.link("회원가입", "/signup").classes(
                "font-bold no-underline"
            )


@ui.page("/signup")
def signup_page():
    add_style()
    _, set_theme = apply_theme()

    with ui.row().classes("w-full items-center justify-between"):
        ui.button(
            "로그인으로",
            icon="arrow_back",
            on_click=lambda: ui.navigate.to("/login"),
        ).props("flat no-caps")
        theme_menu(set_theme)

    with ui.column().classes("w-full max-w-lg mx-auto mt-12"):
        ui.label("회원가입").classes(
            "text-4xl font-black main-text"
        )
        ui.label(
            "개인 대시보드를 위한 계정을 만듭니다."
        ).classes("muted mb-7")

        name = ui.input("표시 이름").props(
            "outlined"
        ).classes("w-full auth-input")
        email = ui.input("이메일").props(
            "outlined"
        ).classes("w-full auth-input")
        pw = ui.input(
            "비밀번호",
            password=True,
            password_toggle_button=True,
        ).props("outlined").classes("w-full auth-input")
        confirm = ui.input(
            "비밀번호 확인",
            password=True,
            password_toggle_button=True,
        ).props("outlined").classes("w-full auth-input")

        async def do_signup():
            if pw.value != confirm.value:
                ui.notify(
                    "비밀번호가 서로 다릅니다.",
                    type="warning",
                )
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
                    )
                    ui.navigate.to("/login")
            except Exception as exc:
                ui.notify(
                    f"회원가입 실패: {exc}",
                    type="negative",
                )

        ui.button(
            "회원가입",
            on_click=do_signup,
        ).props("unelevated no-caps").classes(
            "w-full primary h-12 mt-2 font-bold"
        )


@ui.page("/oauth/callback")
def oauth_callback():
    add_style()
    apply_theme()

    with ui.column().classes(
        "w-full min-h-[75vh] items-center justify-center"
    ):
        ui.spinner(size="lg")
        ui.label(
            "로그인을 완료하고 있습니다..."
        ).classes("muted mt-4")

    async def finish():
        try:
            fragment = await ui.run_javascript(
                "window.location.hash || ''"
            )
            params = parse_qs(str(fragment).lstrip("#"))
            access = params.get("access_token", [None])[0]
            refresh = params.get("refresh_token", [None])[0]
            if access and refresh:
                app.storage.user["access_token"] = access
                app.storage.user["refresh_token"] = refresh
                ui.navigate.to("/dashboard")
                return
            err = params.get(
                "error_description",
                params.get("error", [None]),
            )[0]
            ui.notify(
                f"소셜 로그인 실패: {err or '토큰 없음'}",
                type="negative",
            )
            ui.navigate.to("/login")
        except Exception as exc:
            ui.notify(
                f"OAuth 처리 실패: {exc}",
                type="negative",
            )
            ui.navigate.to("/login")

    ui.timer(0.4, finish, once=True)


@ui.page("/dashboard", response_timeout=15)
async def personal_dashboard():
    add_style()
    _, set_theme = apply_theme()

    if not logged_in():
        ui.navigate.to("/login")
        return

    with ui.row().classes("w-full items-center justify-between"):
        ui.button(
            "시장 홈",
            icon="public",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat no-caps")
        with ui.row().classes("items-center gap-2"):
            theme_menu(set_theme)
            account_host = ui.row()

    ui.label("PERSONAL DASHBOARD").classes(
        "text-[11px] tracking-[.18em] font-bold muted mt-5"
    )
    ui.label("MY MARKET").classes(
        "text-4xl font-black main-text"
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
        user, profile, watchlist, macro = await asyncio.gather(
            asyncio.to_thread(get_user, app.storage.user),
            asyncio.to_thread(get_profile, app.storage.user),
            asyncio.to_thread(load_watchlist, app.storage.user),
            asyncio.to_thread(get_macro_overview),
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

    with account_host:
        with ui.button(
            display_name,
            icon="account_circle",
        ).props("flat no-caps"):
            with ui.menu():
                ui.menu_item(
                    "시장 홈",
                    lambda: ui.navigate.to("/"),
                )
                ui.menu_item("로그아웃", logout)

    with stats:
        for label, value, note in [
            ("ACCOUNT", display_name, "Supabase Auth"),
            (
                "KIS",
                "CONNECTED" if kis.enabled() else "NOT CONFIGURED",
                "한국주식 시세",
            ),
            ("WATCHLIST", str(len(watchlist)), "내 관심종목"),
        ]:
            with ui.card().classes("surface p-5"):
                ui.label(label).classes(
                    "text-xs font-bold muted"
                )
                ui.label(value).classes(
                    "text-xl font-black main-text mt-2"
                )
                ui.label(note).classes("text-xs muted")

    with search_host:
        ui.label("종목 검색").classes("section-title")
        search = ui.input(
            placeholder="삼성, 005930, NVDA, NVIDIA, AAPL"
        ).props("outlined clearable").classes(
            "w-full search-box mt-2"
        )
        results = ui.column().classes("w-full gap-2 mt-1")

    with watch_host:
        ui.label("내 관심종목").classes("section-title")
        watch_grid = ui.grid(columns=3).classes(
            "w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1"
        )

    quote_refs = {}

    async def refresh_quotes():
        jobs = []

        async def one(refs):
            item = refs["item"]
            try:
                q = (
                    await asyncio.to_thread(
                        kis.get_domestic_quote,
                        item["symbol"],
                    )
                    if item["market"] == "KR"
                    else await asyncio.to_thread(
                        get_us_quote,
                        item["symbol"],
                    )
                )
                p = q.get("price")
                ch = q.get("change")
                pct = q.get("change_percent")
                if q.get("currency") == "KRW":
                    refs["price"].set_text(
                        "-" if p is None else f"{p:,.0f}원"
                    )
                    refs["change"].set_text(
                        "-" if ch is None or pct is None
                        else f"{ch:+,.0f}원 ({pct:+.2f}%)"
                    )
                else:
                    refs["price"].set_text(
                        "-" if p is None else f"${p:,.2f}"
                    )
                    refs["change"].set_text(
                        "-" if ch is None or pct is None
                        else f"${ch:+,.2f} ({pct:+.2f}%)"
                    )
            except Exception:
                refs["price"].set_text("조회 실패")

        for refs in quote_refs.values():
            jobs.append(one(refs))
        if jobs:
            await asyncio.gather(*jobs)

    async def render_watchlist():
        watch_grid.clear()
        quote_refs.clear()
        with watch_grid:
            if not watchlist:
                with ui.card().classes("surface p-7"):
                    ui.label(
                        "아직 저장한 관심종목이 없습니다."
                    ).classes("font-bold main-text")
                    ui.label(
                        "위 검색창에서 종목을 추가해보세요."
                    ).classes("text-sm muted")
                return

            for item in watchlist:
                with ui.card().classes(
                    "surface stock-card p-5 min-h-[245px]"
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
                        "text-lg font-bold main-text"
                    )
                    ui.label(
                        f"{item['symbol']} · {item['exchange']}"
                    ).classes("text-xs muted")
                    price = ui.label(
                        "불러오는 중..."
                    ).classes(
                        "text-2xl font-black main-text mt-4"
                    )
                    change = ui.label("-").classes(
                        "text-sm font-bold muted"
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

                    ui.button(
                        "삭제",
                        on_click=remove,
                    ).props("flat dense").classes("w-full mt-4")

                    quote_refs[item["symbol"]] = {
                        "item": item,
                        "price": price,
                        "change": change,
                    }

        await refresh_quotes()

    search_generation = {"n": 0}

    async def do_personal_search():
        search_generation["n"] += 1
        n = search_generation["n"]
        q = (search.value or "").strip()
        results.clear()
        if not q:
            return

        found = await asyncio.to_thread(search_stocks, q)
        if n != search_generation["n"]:
            return

        with results:
            for item in found[:8]:
                with ui.card().classes(
                    "w-full surface px-4 py-3"
                ):
                    with ui.row().classes(
                        "w-full items-center justify-between"
                    ):
                        with ui.column().classes("gap-0"):
                            ui.label(item["name"]).classes(
                                "font-bold main-text"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']} · {item['market']}"
                            ).classes("text-xs muted")

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

                        ui.button(
                            "추가",
                            icon="add",
                            on_click=add,
                        ).props("unelevated").classes("primary")

    search.on(
        "update:model-value",
        lambda _: do_personal_search(),
        throttle=0.28,
        leading_events=False,
        trailing_events=True,
    )

    await render_watchlist()
    ui.timer(REFRESH_SECONDS, refresh_quotes)

    with macro_host:
        ui.label("주요 경제지표").classes("section-title")
        with ui.grid(columns=4).classes(
            "w-full gap-3 mt-3 max-md:grid-cols-2"
        ):
            for item in macro:
                with ui.card().classes("surface p-4"):
                    ui.label(item["name"]).classes(
                        "text-xs font-bold muted"
                    )
                    ui.label(
                        "-" if item["value"] is None
                        else f"{item['value']:.2f}{item['suffix']}"
                    ).classes(
                        "text-xl font-black main-text"
                    )

    with news_host:
        ui.label("내 관심종목 뉴스").classes("section-title")
        news_list = ui.column().classes(
            "w-full surface px-5 mt-3"
        )

    async def load_personal_news():
        data = await asyncio.to_thread(
            get_watchlist_news,
            watchlist,
            8,
        )
        news_list.clear()
        with news_list:
            if not data:
                ui.label("표시할 뉴스가 없습니다.").classes(
                    "py-5 muted"
                )
            for item in data:
                with ui.column().classes(
                    "w-full py-4 border-b border-[var(--border)] "
                    "last:border-0 gap-1"
                ):
                    if item.get("url"):
                        ui.link(
                            item["title"],
                            item["url"],
                            new_tab=True,
                        ).classes(
                            "main-text font-semibold no-underline"
                        )
                    else:
                        ui.label(item["title"]).classes(
                            "main-text font-semibold"
                        )
                    ui.label(
                        " · ".join(
                            x for x in [
                                item.get("symbol", ""),
                                item.get("publisher", ""),
                            ] if x
                        )
                    ).classes("text-xs muted")

    await load_personal_news()


@ui.page(
    "/stock/{market}/{exchange}/{symbol}",
    response_timeout=15,
)
async def stock_detail(market, exchange, symbol):
    add_style()
    _, set_theme = apply_theme()

    with ui.row().classes(
        "w-full items-center justify-between sticky top-0 z-10 py-3"
    ):
        ui.button(
            "이전 화면",
            icon="arrow_back",
            on_click=lambda: ui.run_javascript("history.back()"),
        ).props("flat no-caps")
        with ui.row().classes("gap-2"):
            theme_menu(set_theme)
            ui.button(
                "시장 홈",
                icon="public",
                on_click=lambda: ui.navigate.to("/"),
            ).props("flat no-caps")
            if logged_in():
                ui.button(
                    "내 대시보드",
                    icon="dashboard",
                    on_click=lambda: ui.navigate.to("/dashboard"),
                ).props("flat no-caps")

    name_label = ui.label(symbol).classes(
        "text-3xl font-black main-text mt-5"
    )
    ui.label(
        f"{symbol} · {exchange} · {market}"
    ).classes("text-sm muted")

    with ui.card().classes("surface p-5 mt-5"):
        price_label = ui.label(
            "가격 불러오는 중..."
        ).classes("text-3xl font-black main-text")
        change_label = ui.label("-").classes(
            "text-sm font-bold muted"
        )

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
    ).props("outlined use-chips").classes(
        "w-full max-w-xl mt-3"
    )
    chart_host = ui.column().classes(
        "w-full chart-wrap min-h-[560px] mt-4"
    )
    with chart_host:
        ui.spinner(size="lg").classes("m-auto mt-24")

    await ui.context.client.connected()

    try:
        found = await asyncio.to_thread(search_stocks, symbol)
        exact = next(
            (
                x for x in found
                if x["market"] == market
                and x["symbol"] == symbol
            ),
            None,
        )
        if exact:
            name_label.set_text(exact["name"])
    except Exception:
        pass

    async def load_quote():
        try:
            q = (
                await asyncio.to_thread(
                    kis.get_domestic_quote,
                    symbol,
                )
                if market == "KR"
                else await asyncio.to_thread(
                    get_us_quote,
                    symbol,
                )
            )
            p, c, pct = (
                q.get("price"),
                q.get("change"),
                q.get("change_percent"),
            )
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
            change_label.set_text(str(exc)[:80])

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
                    ).classes("negative p-6")

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

    await asyncio.gather(load_quote(), render_chart())


@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now().isoformat()}


ui.run(
    host="0.0.0.0",
    port=PORT,
    title="My Market",
    favicon="📈",
    dark=None,
    show=False,
    reload=False,
    storage_secret=STORAGE_SECRET,
)
