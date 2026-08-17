import asyncio
import json
import os
from datetime import datetime
from urllib.parse import parse_qs, quote
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from nicegui import app, ui

from chart_data import get_echart_options
from bond_ui import render_bond_panel
from data_engine import engine
from global_market_data import (
    get_futures_snapshot,
    get_fx_snapshot,
    get_us_yield_curve,
    get_kr_yield_curve,
    get_us_extended_session,
    get_us_extended_batch,
    get_us_bond_history,
    get_kr_bond_history,
    get_us_spread_history,
    get_kr_spread_history,
    line_chart_options,
    get_ecos_diagnostics,
)
from indicator_data import make_indicator_options, MARKET_LABELS, MACRO_LABELS
from dashboard_data import (
    get_macro_overview,
    get_market_overview,
    get_watchlist_news,
    get_sparkline_svg,
)
from kis import KISClient
from kr_master import load_master
from market_data import get_us_quote, search_stocks
from heatmap_data import get_us_heatmap, get_kr_heatmap, echart_treemap
from realtime_market import USRealtimeHub
from realtime_kr import KRRealtimeHub
from news_data import (
    get_naver_news_for_watchlist, merge_news, naver_news_enabled,
)
from public_data import get_representative_stocks
from portfolio_lab import (
    compare_rebalance_strategies,
    contribution_rebalance,
    drift_analysis,
    drift_timeline,
    stress_tests,
    what_if,
    xray,
)
from supabase_store import (
    add_watchlist,
    delete_watchlist,
    get_profile,
    get_user,
    load_watchlist,
    load_portfolio,
    get_user_preferences,
    save_base_currency,
    upsert_position,
    delete_position,
    load_target_allocations,
    upsert_target_allocation,
    get_rebalance_rule,
    upsert_rebalance_rule,
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
us_realtime = USRealtimeHub(
    os.getenv('KIS_APP_KEY', ''),
    os.getenv('KIS_APP_SECRET', ''),
    os.getenv('KIS_ENV', 'real'),
    fallback_provider=get_us_extended_batch,
)
kr_realtime = KRRealtimeHub(
    os.getenv('KIS_APP_KEY', ''),
    os.getenv('KIS_APP_SECRET', ''),
    os.getenv('KIS_ENV', 'real'),
)

# Shared background cache. These feeds start warming when the Render process starts,
# not when a user opens a page.
engine.register('markets', get_market_overview, 30)
engine.register('macro', get_macro_overview, 900)
engine.register('futures', get_futures_snapshot, 60)
engine.register('fx', get_fx_snapshot, 60)
engine.register('us_curve', get_us_yield_curve, 600)
engine.register('kr_curve', get_kr_yield_curve, 600)
engine.register('us_heat', get_us_heatmap, 180)
engine.register('kr_heat', lambda: get_kr_heatmap(kis, 24), 180)
app.on_startup(engine.start)
app.on_shutdown(engine.stop)



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
                min-height:36px!important;
                padding:0 15px!important;
                color:var(--text)!important;
                font-weight:700!important;
                opacity:.72;
            }
            .q-btn.filter-button:hover {
                opacity:1;
                background:var(--surface-2)!important;
            }
            .q-btn.filter-active {
                background:var(--blue)!important;
                color:white!important;
                opacity:1!important;
                box-shadow:0 2px 8px rgba(37,99,235,.22);
            }
            body.body--dark .q-btn.filter-button:not(.filter-active) {
                color:#d7e0ec!important;
                opacity:.82;
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
            .watch-card {
                height:420px;
                display:flex!important;
                flex-direction:column!important;
            }
            .watch-name-block { min-height:70px; }
            .watch-name {
                line-height:1.35;
                min-height:46px;
                display:-webkit-box;
                -webkit-line-clamp:2;
                -webkit-box-orient:vertical;
                overflow:hidden;
            }
            .watch-price-block { min-height:76px; }
            .watch-spark { height:88px; }
            .watch-actions { margin-top:auto; }
            .dashboard-tabs .q-tab { min-height:46px; font-weight:700; }
            .dashboard-tabs .q-tab--active { color:var(--blue)!important; }
            .currency-switch { border:1px solid var(--border); border-radius:12px; padding:4px; background:var(--surface); }

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


def live_spark_options(points, positive=True):
    values = [round(float(p[1]), 4) for p in (points or [])[-120:]]
    labels = [datetime.fromtimestamp(float(p[0]), ZoneInfo("America/New_York")).strftime("%H:%M:%S") for p in (points or [])[-120:]]
    color = "#ff4d57" if positive else "#4594ff"
    return {
        "animation": False,
        "backgroundColor": "transparent",
        "grid": {"left": 2, "right": 2, "top": 5, "bottom": 3},
        "xAxis": {"type": "category", "data": labels, "show": False, "boundaryGap": False},
        "yAxis": {"type": "value", "show": False, "scale": True},
        "tooltip": {"trigger": "axis", "formatter": "{c}"},
        "series": [{
            "type": "line",
            "data": values,
            "showSymbol": False,
            "smooth": False,
            "connectNulls": True,
            "lineStyle": {"width": 2, "color": color},
            "areaStyle": {"opacity": 0.04, "color": color},
        }],
    }


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
    global_host = ui.column().classes("w-full mt-8")
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
        with market_grid:
            ui.spinner(size="md").classes("m-6")

    with global_host:
        ui.label("글로벌 시장").classes("section-title")
        ui.label("선물·환율·국채 금리를 한 화면에서 확인합니다.").classes("text-xs muted mb-3")
        with ui.tabs().classes("w-full dashboard-tabs") as global_tabs:
            futures_tab = ui.tab("선물", icon="candlestick_chart")
            fx_tab = ui.tab("환율", icon="currency_exchange")
            bonds_tab = ui.tab("채권", icon="timeline")
            heatmap_tab = ui.tab("히트맵", icon="grid_view")
        with ui.tab_panels(global_tabs, value=futures_tab).classes("w-full bg-transparent"):
            with ui.tab_panel(futures_tab).classes("p-0"):
                public_futures = ui.grid(columns=4).classes("w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1")
            with ui.tab_panel(fx_tab).classes("p-0"):
                public_fx = ui.grid(columns=4).classes("w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1")
            with ui.tab_panel(bonds_tab).classes("p-0"):
                public_bonds = ui.column().classes("w-full mt-3 gap-4")
            with ui.tab_panel(heatmap_tab).classes("p-0"):
                public_heatmap = ui.column().classes("w-full mt-3 gap-4")

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

        stock_grid = ui.grid(columns=4).classes(
            "w-full gap-3 mt-4 max-xl:grid-cols-3 max-lg:grid-cols-2 max-md:grid-cols-1"
        )
        with stock_grid:
            ui.spinner(size="md").classes("m-8")

    with macro_host:
        ui.label("주요 경제지표").classes("section-title")
        macro_grid = ui.grid(columns=4).classes(
            "w-full gap-3 mt-3 max-md:grid-cols-2"
        )
        with macro_grid:
            ui.spinner(size="md").classes("m-6")

    with news_host:
        ui.label("시장 뉴스").classes("section-title")
        news_list = ui.column().classes(
            "w-full surface px-5 mt-3 min-h-[150px]"
        )
        with news_list:
            ui.spinner(size="md").classes("m-auto mt-10")

    await ui.context.client.connected()

    # Warm the full KOSPI/KOSDAQ search index in the background.
    asyncio.create_task(asyncio.to_thread(load_master))

    state = {"market": "KR", "mode": "cap"}

    async def load_markets():
        data = await asyncio.to_thread(get_market_overview)
        market_grid.clear()
        with market_grid:
            for item in data:
                with ui.card().classes(
                    "surface market-card p-4 min-h-[145px]"
                ) as market_card:
                    market_card.on(
                        "click",
                        lambda _, x=item: ui.navigate.to(
                            f"/indicator/market/{quote(x['symbol'], safe='')}"
                        ),
                    )
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

    async def load_global_snapshot():
        keys = ["futures", "fx", "us_curve", "kr_curve", "us_heat", "kr_heat"]
        missing = [k for k in keys if engine.get(k) is None]
        if missing:
            await asyncio.gather(*(engine.refresh(k) for k in missing))
        futures = engine.get("futures", [])
        fx = engine.get("fx", [])
        us_curve = engine.get("us_curve", [])
        kr_curve = engine.get("kr_curve", [])
        us_heat = engine.get("us_heat", [])
        kr_heat = engine.get("kr_heat", [])

        def render_cards(host, rows, value_fmt):
            host.clear()
            with host:
                for item in rows:
                    pct = item.get("percent")
                    with ui.card().classes("surface p-4"):
                        ui.label(item["name"]).classes("text-xs font-bold muted")
                        value = item.get("value")
                        ui.label("-" if value is None else value_fmt(item)).classes("text-xl font-black main-text mt-1")
                        if pct is not None:
                            ui.label(f"{pct:+.2f}%").classes(f"text-xs font-bold {delta_class(pct)}")
                        svg = mini_svg(item.get("spark") or [], height=34)
                        if svg:
                            ui.html(svg).classes("w-full mt-2")

        render_cards(public_futures, futures, lambda x: f"{x['value']:,.2f}")
        render_cards(public_fx, fx, lambda x: f"{x['value']:,.4f}" if abs(x['value']) < 100 else f"{x['value']:,.2f}")

        await render_bond_panel(public_bonds, us_curve, kr_curve)

        public_heatmap.clear()
        with public_heatmap:
            with ui.tabs().classes('w-full dashboard-tabs') as hm_tabs:
                hm_us = ui.tab('미국', icon='flag')
                hm_kr = ui.tab('한국', icon='flag')
            with ui.tab_panels(hm_tabs, value=hm_us).classes('w-full bg-transparent'):
                with ui.tab_panel(hm_us).classes('p-0'):
                    ui.echart(echart_treemap(us_heat, 'US Large Cap Heatmap'), renderer='canvas').classes('w-full h-[520px] surface')
                with ui.tab_panel(hm_kr).classes('p-0'):
                    if kr_heat:
                        ui.echart(echart_treemap(kr_heat, 'Korea Market Cap Heatmap'), renderer='canvas').classes('w-full h-[520px] surface')
                    else:
                        ui.label('한국 히트맵 데이터를 불러오지 못했습니다.').classes('muted p-5')

    def paint_filter_buttons():
        pairs = [
            (kr_btn, state["market"] == "KR"),
            (us_btn, state["market"] == "US"),
            (cap_btn, state["mode"] == "cap"),
            (volume_btn, state["mode"] == "volume"),
        ]
        for button, active in pairs:
            button.classes(remove="filter-active")
            if active:
                button.classes(add="filter-active")

    public_stock_refs = {}

    def refresh_public_live():
        current_market = state.get('market')
        for symbol, refs in list(public_stock_refs.items()):
            hub = us_realtime if current_market == 'US' else kr_realtime
            snap = hub.get(symbol)
            value = snap.get('display_last')
            pct = snap.get('display_percent')
            if value is not None:
                refs['price'].set_text(
                    f"${float(value):,.2f}" if current_market == 'US' else f"{float(value):,.0f}원"
                )
            if pct is not None:
                refs['pct'].set_text(f"{float(pct):+.2f}%")
                refs['pct'].classes(remove='positive negative muted')
                refs['pct'].classes(add=delta_class(float(pct)))

            seq = int(snap.get('tick_seq', 0))
            points = snap.get('live_points') or []
            if points and seq != refs.get('tick_seq'):
                chart = refs.get('spark_chart')
                if chart is not None:
                    opts = live_spark_options(points, positive=(pct or 0) >= 0)
                    chart.options.clear(); chart.options.update(opts); chart.update()
                    refs['tick_seq'] = seq

            session = snap.get('session', 'CLOSED')
            session_short = {
                'PRE': '장전', 'REGULAR': '본장', 'CLOSING': '동시호가',
                'AFTER': '시간외', 'POST': 'POST', 'CLOSED': '마감'
            }.get(session, session)
            refs['session'].classes(remove='muted positive negative')
            if snap.get('state') == 'LIVE':
                label = f"● {session_short} LIVE"
                refs['session'].classes(add='positive' if (pct or 0) >= 0 else 'negative')
            elif current_market == 'US' and snap.get('state') == 'QUOTE':
                label = f"● {session_short} QUOTE LIVE"
                refs['session'].classes(add='positive' if (pct or 0) >= 0 else 'negative')
            elif snap.get('state') in ('READY', 'ACKED'):
                label = f"● {session_short} · WS READY"
                refs['session'].classes(add='muted')
            elif value is not None:
                label = f"● {session_short} · SNAPSHOT"
                refs['session'].classes(add='muted')
            else:
                label = '' if session == 'CLOSED' else f'{session_short} · 시세 준비중'
                refs['session'].classes(add='muted')
            refs['session'].set_text(label)

    async def load_stocks():
        data = await asyncio.to_thread(
            get_representative_stocks,
            state["market"],
            state["mode"],
            12,
            kis=kis,
        )
        stock_grid.clear()
        public_stock_refs.clear()

        with stock_grid:
            for item in data:
                with ui.card().classes(
                    "surface stock-card p-5 min-h-[235px]"
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
                        with ui.column().classes("gap-0 min-w-0"): 
                            ui.label(item["name"]).classes(
                                "font-bold main-text text-lg leading-snug line-clamp-2 min-h-[44px]"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']}"
                            ).classes("text-xs muted")
                        ui.label(item["market"]).classes(
                            "pill text-[10px] font-bold shrink-0"
                        )

                    price_ref = ui.label(stock_price_text(item)).classes(
                        "text-2xl font-black main-text mt-3"
                    )
                    pct = item.get("percent")
                    pct_ref = ui.label(
                        "-" if pct is None else f"{pct:+.2f}%"
                    ).classes(
                        f"text-sm font-bold {delta_class(pct)}"
                    )
                    session_ref = ui.label("").classes(
                        "text-[10px] muted min-h-[16px] mt-1"
                    )

                    seed = [[i, v] for i, v in enumerate(item.get("spark") or [])]
                    spark_chart = ui.echart(
                        live_spark_options(seed, positive=(pct or 0) >= 0),
                        renderer="canvas",
                    ).classes("w-full h-[72px] mt-2")
                    ui.label("클릭해서 상세 차트").classes(
                        "text-[11px] soft mt-1"
                    )

                    public_stock_refs[item["symbol"]] = {
                        "price": price_ref,
                        "pct": pct_ref,
                        "session": session_ref,
                        "exchange": item.get("exchange", ""),
                        "market": item.get("market", ""),
                        "spark_chart": spark_chart,
                        "tick_seq": -1,
                    }
                    if item.get("market") == "KR":
                        kr_realtime.seed(
                            item["symbol"], item.get("price"), item.get("percent"),
                            item.get("change"), item.get("spark") or []
                        )

        if public_stock_refs:
            if state["market"] == "US":
                await us_realtime.subscribe_many(
                    [(symbol, refs["exchange"]) for symbol, refs in public_stock_refs.items()]
                )
            else:
                await kr_realtime.subscribe_many(list(public_stock_refs))
            await asyncio.sleep(0)
            refresh_public_live()

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
                with ui.card().classes("surface market-card p-4") as macro_card:
                    macro_card.on(
                        "click",
                        lambda _, x=item: ui.navigate.to(
                            f"/indicator/macro/{quote(x['id'], safe='')}"
                        ),
                    )
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

    # v1.3: do not hold the HTTP page response for upstream market APIs.
    # The user sees the shell immediately while cached/background feeds paint in.
    asyncio.create_task(load_markets())
    asyncio.create_task(load_stocks())
    asyncio.create_task(load_global_snapshot())
    asyncio.create_task(load_macro())
    asyncio.create_task(load_news())

    ui.timer(30, load_markets)
    ui.timer(1.0, refresh_public_live)
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
            "시장 홈", icon="public", on_click=lambda: ui.navigate.to("/")
        ).props("flat no-caps")
        with ui.row().classes("items-center gap-2"):
            theme_menu(set_theme)
            account_host = ui.row()

    ui.label("PERSONAL INVESTMENT DASHBOARD").classes(
        "text-[11px] tracking-[.18em] font-bold muted mt-5"
    )
    ui.label("MY MARKET").classes("text-4xl font-black main-text")

    with ui.tabs().classes("w-full dashboard-tabs mt-6") as dashboard_tabs:
        overview_tab = ui.tab("Overview", icon="space_dashboard")
        portfolio_tab = ui.tab("Portfolio", icon="account_balance_wallet")
        lab_tab = ui.tab("Portfolio Lab", icon="science")
        market_tab = ui.tab("Market", icon="monitoring")
        news_tab = ui.tab("News", icon="newspaper")

    with ui.tab_panels(dashboard_tabs, value=overview_tab).classes("w-full bg-transparent"):
        with ui.tab_panel(overview_tab).classes("p-0"):
            summary_host = ui.column().classes("w-full mt-5")
            market_host = ui.column().classes("w-full mt-9")
            search_host = ui.column().classes("w-full mt-9")
            watch_host = ui.column().classes("w-full mt-9")
        with ui.tab_panel(portfolio_tab).classes("p-0"):
            portfolio_host = ui.column().classes("w-full mt-5")
        with ui.tab_panel(lab_tab).classes("p-0"):
            lab_host = ui.column().classes("w-full mt-5")
        with ui.tab_panel(market_tab).classes("p-0"):
            macro_host = ui.column().classes("w-full mt-5")
        with ui.tab_panel(news_tab).classes("p-0"):
            news_host = ui.column().classes("w-full mt-5")

    await ui.context.client.connected()

    try:
        (
            user,
            profile,
            watchlist,
            portfolio,
            macro,
            targets,
            rebalance_rule,
            market_snapshot,
            preferences,
        ) = await asyncio.gather(
            asyncio.to_thread(get_user, app.storage.user),
            asyncio.to_thread(get_profile, app.storage.user),
            asyncio.to_thread(load_watchlist, app.storage.user),
            asyncio.to_thread(load_portfolio, app.storage.user),
            asyncio.to_thread(get_macro_overview),
            asyncio.to_thread(load_target_allocations, app.storage.user),
            asyncio.to_thread(get_rebalance_rule, app.storage.user),
            asyncio.to_thread(get_market_overview),
            asyncio.to_thread(get_user_preferences, app.storage.user),
        )
        if not user:
            raise RuntimeError("사용자 확인 실패")
    except Exception as exc:
        ui.notify(f"개인 데이터 로딩 실패: {exc}", type="negative")
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
        with ui.button(display_name, icon="account_circle").props("flat no-caps"):
            with ui.menu():
                ui.menu_item("시장 홈", lambda: ui.navigate.to("/"))
                ui.menu_item("로그아웃", logout)

    usdkrw = next(
        (x.get("value") for x in market_snapshot if x.get("symbol") == "KRW=X"),
        None,
    ) or 1.0

    base_currency = {"value": str((preferences or {}).get("base_currency") or "KRW").upper()}

    def base_amount(krw_value):
        value = float(krw_value or 0)
        return value if base_currency["value"] == "KRW" else value / float(usdkrw or 1)

    def money_text_from_krw(krw_value, signed=False):
        value = base_amount(krw_value)
        sign = "+" if signed and value > 0 else ""
        if base_currency["value"] == "KRW":
            return f"{sign}₩{value:,.0f}"
        return f"{sign}${value:,.2f}"

    async def valued_positions():
        async def one(position):
            try:
                quote_data = (
                    await asyncio.to_thread(kis.get_domestic_quote, position["symbol"])
                    if position["market"] == "KR"
                    else await asyncio.to_thread(get_us_quote, position["symbol"])
                )
                raw_price = quote_data.get("price")
                current = float(raw_price) if raw_price not in (None, "") else None
            except Exception:
                current = None
            qty = float(position.get("quantity") or 0)
            avg = float(position.get("average_price") or 0)
            fx = 1.0 if position["market"] == "KR" else float(usdkrw)
            local_cost = avg * qty
            local_value = current * qty if current is not None else None
            local_pnl = local_value - local_cost if local_value is not None else None
            return {
                "position": position,
                "current": current,
                "priced": current is not None,
                "local_value": local_value,
                "local_cost": local_cost,
                "local_pnl": local_pnl,
                "fx": fx,
                "value_krw": local_value * fx if local_value is not None else None,
                "cost_krw": local_cost * fx,
            }

        if not portfolio:
            return []
        return await asyncio.gather(*(one(p) for p in portfolio))

    valuation_rows = await valued_positions()

    def valuation_totals(rows):
        priced = [r for r in rows if r.get("priced") and r.get("value_krw") is not None]
        value = sum(float(r["value_krw"]) for r in priced)
        cost = sum(float(r["cost_krw"]) for r in priced)
        pnl = value - cost
        rate = pnl / cost * 100 if cost else 0.0
        missing = len(rows) - len(priced)
        return value, cost, pnl, rate, missing


    async def render_summary():
        summary_host.clear()
        value, cost, pnl, rate, missing = valuation_totals(valuation_rows)
        with summary_host:
            with ui.row().classes("w-full items-center justify-between gap-3"):
                ui.label("내 자산 요약").classes("section-title")
                with ui.row().classes("currency-switch items-center gap-1"):
                    krw_button = ui.button("KRW").props("flat dense no-caps")
                    usd_button = ui.button("USD").props("flat dense no-caps")

                    def paint_currency():
                        for button, active in [
                            (krw_button, base_currency["value"] == "KRW"),
                            (usd_button, base_currency["value"] == "USD"),
                        ]:
                            button.classes(remove="filter-active")
                            if active:
                                button.classes(add="filter-active")

                    async def change_currency(currency):
                        base_currency["value"] = currency
                        paint_currency()
                        try:
                            await asyncio.to_thread(
                                save_base_currency,
                                app.storage.user,
                                currency,
                            )
                        except Exception as exc:
                            ui.notify(f"기준통화 저장 실패: {exc}", type="warning")
                        await render_summary()
                        await render_portfolio()
                        await render_lab()

                    krw_button.on_click(lambda: change_currency("KRW"))
                    usd_button.on_click(lambda: change_currency("USD"))
                    paint_currency()

            with ui.grid(columns=4).classes(
                "w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1"
            ):
                cards = [
                    ("총 평가자산", money_text_from_krw(value), f"기준통화 {base_currency['value']}"),
                    ("투자원금", money_text_from_krw(cost), "현재가 조회 가능 포지션 기준"),
                    ("평가손익", money_text_from_krw(pnl, signed=True), f"{rate:+.2f}%"),
                    ("관심종목", str(len(watchlist)), f"포트폴리오 {len(portfolio)}종목"),
                ]
                for title, primary, secondary in cards:
                    with ui.card().classes("surface p-5"):
                        ui.label(title).classes("text-xs font-bold muted")
                        ui.label(primary).classes("text-2xl font-black main-text mt-2")
                        ui.label(secondary).classes("text-xs muted")
            if missing:
                ui.label(
                    f"현재가를 받지 못한 {missing}개 포지션은 총 평가/손익에서 제외했습니다."
                ).classes("text-xs negative mt-2")

    await render_summary()

    # Same market context as the public home: login should add information, not remove it.
    with market_host:
        with ui.row().classes("w-full items-end justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("시장 한눈에 보기").classes("section-title")
                ui.label("로그인 전 시장 화면을 개인 대시보드에서도 그대로 봅니다.").classes("text-xs muted")
        with ui.grid(columns=7).classes(
            "w-full gap-2 mt-3 max-xl:grid-cols-4 max-md:grid-cols-2"
        ):
            for item in market_snapshot:
                with ui.card().classes("surface market-card p-4 min-h-[140px]") as card:
                    async def open_indicator(current=item):
                        ui.navigate.to(f"/indicator/market/{quote(current['symbol'], safe='')}")
                    card.on("click", open_indicator)
                    ui.label(item["name"]).classes("text-xs font-bold muted")
                    ui.label(market_value_text(item)).classes("text-lg font-black main-text")
                    pct = item.get("percent")
                    ui.label("-" if pct is None else f"{pct:+.2f}%").classes(
                        f"text-xs font-bold {delta_class(pct)}"
                    )
                    svg = mini_svg(item.get("spark") or [], height=40)
                    if svg:
                        ui.html(svg).classes("w-full mt-2")

    with search_host:
        ui.label("종목 검색").classes("section-title")
        search = ui.input(
            placeholder="삼성, 한화, 005930, NVDA, NVIDIA, AAPL"
        ).props("outlined clearable").classes("w-full search-box mt-2")
        results = ui.column().classes("w-full gap-2 mt-1")

    search_generation = {"n": 0}

    async def do_search():
        search_generation["n"] += 1
        generation = search_generation["n"]
        query = (search.value or "").strip()
        results.clear()
        if not query:
            return
        found = await asyncio.to_thread(search_stocks, query)
        if generation != search_generation["n"]:
            return
        with results:
            for item in found[:10]:
                with ui.card().classes("w-full surface px-4 py-3"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(item["name"]).classes("font-bold main-text")
                            ui.label(
                                f"{item['symbol']} · {item['exchange']} · {item['market']}"
                            ).classes("text-xs muted")

                        async def add(current=item):
                            saved = await asyncio.to_thread(
                                add_watchlist, app.storage.user, current
                            )
                            if not any(
                                x["market"] == current["market"]
                                and x["exchange"] == current["exchange"]
                                and x["symbol"] == current["symbol"]
                                for x in watchlist
                            ):
                                watchlist.append(saved or current)
                            search.set_value("")
                            results.clear()
                            await render_watchlist()

                        ui.button("관심종목", icon="star", on_click=add).props(
                            "flat dense no-caps"
                        )

    search.on(
        "update:model-value",
        lambda _: do_search(),
        throttle=0.28,
        leading_events=False,
        trailing_events=True,
    )

    with watch_host:
        ui.label("내 관심종목").classes("section-title")
        ui.label("카드 전체 클릭을 제거해 버튼 오작동을 막았습니다.").classes("text-xs muted")
        watch_grid = ui.grid(columns=3).classes(
            "w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1"
        )

    quote_refs = {}

    async def edit_position(item, existing=None):
        with ui.dialog() as dialog, ui.card().classes("surface w-full max-w-md p-6"):
            ui.label(f"{item['name']} 포트폴리오").classes("text-xl font-black main-text")
            currency = "KRW" if item["market"] == "KR" else "USD"
            currency_symbol = "₩" if currency == "KRW" else "$"
            ui.label(f"입력 통화: {currency} ({currency_symbol})").classes("text-sm font-bold muted")
            qty = ui.number(
                "보유수량",
                value=float((existing or {}).get("quantity") or 0),
                min=0.000001,
                step=0.01,
            ).props("outlined").classes("w-full")
            avg = ui.number(
                f"평균매입단가 ({currency})",
                value=float((existing or {}).get("average_price") or 0),
                min=0.000001,
                step=1 if currency == "KRW" else 0.01,
            ).props("outlined").classes("w-full")

            async def save():
                nonlocal valuation_rows
                try:
                    quantity = float(qty.value)
                    average_price = float(avg.value)
                except (TypeError, ValueError):
                    ui.notify("수량과 평단을 숫자로 입력해주세요.", type="warning")
                    return
                if quantity <= 0:
                    ui.notify("보유수량은 0보다 커야 합니다.", type="warning")
                    return
                if average_price <= 0:
                    ui.notify(f"평균매입단가({currency})는 0보다 커야 합니다.", type="warning")
                    return
                saved = await asyncio.to_thread(
                    upsert_position,
                    app.storage.user,
                    item,
                    quantity,
                    average_price,
                )
                index = next(
                    (
                        i for i, p in enumerate(portfolio)
                        if p["market"] == item["market"]
                        and p["exchange"] == item["exchange"]
                        and p["symbol"] == item["symbol"]
                    ),
                    None,
                )
                if index is None:
                    portfolio.append(saved)
                else:
                    portfolio[index] = saved
                dialog.close()
                valuation_rows = await valued_positions()
                await render_summary()
                await render_watchlist()
                await render_portfolio()
                await render_lab()

            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button("취소", on_click=dialog.close).props("flat no-caps")
                ui.button("저장", on_click=save).props("unelevated no-caps").classes("primary")
        dialog.open()

    async def refresh_watch_quotes():
        async def one(refs):
            item = refs['item']
            hub = kr_realtime if item['market'] == 'KR' else us_realtime
            snap = hub.get(item['symbol'])
            price = snap.get('display_last')
            pct = snap.get('display_percent')
            change = snap.get('display_change')

            # Initial/fallback REST only when the hub has no usable value.
            if price is None:
                try:
                    q = (
                        await asyncio.to_thread(kis.get_domestic_quote, item['symbol'])
                        if item['market'] == 'KR'
                        else await asyncio.to_thread(get_us_quote, item['symbol'])
                    )
                    price = q.get('price'); change = q.get('change'); pct = q.get('change_percent')
                    if item['market'] == 'KR' and price is not None:
                        kr_realtime.seed(item['symbol'], price, pct, change)
                except Exception:
                    refs['price'].set_text('조회 실패')
                    return

            if item['market'] == 'KR':
                refs['price'].set_text(f'{float(price):,.0f}원')
                refs['change'].set_text('-' if change is None or pct is None else f'{float(change):+,.0f}원 ({float(pct):+.2f}%)')
            else:
                refs['price'].set_text(f'${float(price):,.2f}')
                refs['change'].set_text('-' if change is None or pct is None else f'${float(change):+,.2f} ({float(pct):+.2f}%)')

            seq = int(snap.get('tick_seq', 0))
            points = snap.get('live_points') or []
            if points and seq != refs.get('tick_seq'):
                opts = live_spark_options(points, positive=(pct or 0) >= 0)
                refs['spark_chart'].options.clear(); refs['spark_chart'].options.update(opts); refs['spark_chart'].update()
                refs['tick_seq'] = seq

            session = snap.get('session', '')
            short = {'PRE':'장전','REGULAR':'본장','CLOSING':'동시호가','AFTER':'시간외','POST':'POST'}.get(session, session)
            if snap.get('state') == 'LIVE':
                refs['live_state'].set_text(f'● {short} LIVE')
            elif snap.get('state') in ('QUOTE','READY','ACKED'):
                refs['live_state'].set_text(f'● {short} · WS READY')
            else:
                refs['live_state'].set_text(f'● {short} · SNAPSHOT' if short else '')

        if quote_refs:
            await asyncio.gather(*(one(x) for x in quote_refs.values()))

    async def render_watchlist():
        watch_grid.clear()
        quote_refs.clear()
        with watch_grid:
            if not watchlist:
                with ui.card().classes("surface p-7"):
                    ui.label("아직 저장한 관심종목이 없습니다.").classes("font-bold main-text")
                return

            for item in watchlist:
                with ui.card().classes("surface p-5 watch-card"):
                    with ui.row().classes("w-full items-start justify-between no-wrap watch-name-block"):
                        with ui.column().classes("gap-0 min-w-0 pr-3"):
                            ui.label(item["name"]).classes(
                                "text-lg font-bold main-text watch-name"
                            )
                            ui.label(
                                f"{item['symbol']} · {item['exchange']}"
                            ).classes("text-xs muted")
                        ui.label(
                            f"{item['market']} · {item['exchange']}"
                        ).classes("pill text-[10px] font-bold shrink-0")

                    with ui.column().classes("gap-1 mt-4 watch-price-block"):
                        price = ui.label("불러오는 중...").classes(
                            "text-2xl font-black main-text"
                        )
                        change = ui.label("-").classes("text-sm font-bold muted")

                    spark_chart = ui.echart(
                        live_spark_options([], positive=True), renderer="canvas"
                    ).classes("w-full watch-spark mt-2")
                    live_state = ui.label("").classes("text-[10px] muted")

                    existing = next(
                        (
                            p for p in portfolio
                            if p["market"] == item["market"]
                            and p["exchange"] == item["exchange"]
                            and p["symbol"] == item["symbol"]
                        ),
                        None,
                    )

                    with ui.column().classes("w-full watch-actions gap-2"):
                        with ui.row().classes("w-full gap-2"):
                            async def detail(current=item):
                                ui.navigate.to(
                                    f"/stock/{current['market']}/"
                                    f"{quote(current['exchange'], safe='')}/"
                                    f"{quote(current['symbol'], safe='')}"
                                )

                            async def portfolio_edit(current=item, current_position=existing):
                                await edit_position(current, current_position)

                            ui.button(
                                "상세", icon="show_chart", on_click=detail
                            ).props("outline dense no-caps").classes("flex-1")
                            ui.button(
                                "포트폴리오",
                                icon="account_balance_wallet",
                                on_click=portfolio_edit,
                            ).props("outline dense no-caps").classes("flex-1")

                        with ui.row().classes("w-full justify-end"):
                            with ui.button(icon="more_horiz").props("flat round dense"):
                                with ui.menu():
                                    async def remove(current=item):
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
                                    ui.menu_item("관심종목 삭제", remove)

                    quote_refs[f"{item['market']}:{item['symbol']}"] = {
                        "item": item,
                        "price": price,
                        "change": change,
                        "spark_chart": spark_chart,
                        "live_state": live_state,
                        "tick_seq": -1,
                    }

        kr_symbols = [x['item']['symbol'] for x in quote_refs.values() if x['item']['market'] == 'KR']
        us_symbols = [(x['item']['symbol'], x['item']['exchange']) for x in quote_refs.values() if x['item']['market'] == 'US']
        if kr_symbols:
            await kr_realtime.subscribe_many(kr_symbols)
        if us_symbols:
            await us_realtime.subscribe_many(us_symbols)
        await refresh_watch_quotes()

    await render_watchlist()
    ui.timer(1.0, refresh_watch_quotes)

    with portfolio_host:
        with ui.row().classes("w-full items-end justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("내 포트폴리오").classes("section-title")
                ui.label("현재가·평단·환율을 합쳐 평가손익과 자산배분을 계산합니다.").classes("text-xs muted")
            portfolio_summary = ui.label("").classes("text-sm font-bold main-text")
        with ui.grid(columns=3).classes(
            "w-full gap-3 mt-3 max-lg:grid-cols-1"
        ):
            portfolio_grid = ui.grid(columns=2).classes("col-span-2 gap-3 max-md:grid-cols-1")
            allocation_host = ui.column().classes("surface p-4 min-h-[300px]")

    async def render_portfolio():
        portfolio_grid.clear()
        allocation_host.clear()
        value, cost, pnl, rate, missing = valuation_totals(valuation_rows)
        portfolio_summary.set_text(
            f"총 평가 {money_text_from_krw(value)} · {money_text_from_krw(pnl, signed=True)} ({rate:+.2f}%)"
        )

        with portfolio_grid:
            if not valuation_rows:
                with ui.card().classes("surface p-7"):
                    ui.label("관심종목의 포트폴리오 버튼에서 수량·평단을 입력하세요.").classes("muted")
            for row in valuation_rows:
                p = row["position"]
                with ui.card().classes("surface p-5"):
                    ui.label(p["name"]).classes("text-lg font-bold main-text")
                    ui.label(f"{p['symbol']} · {p['exchange']}").classes("text-xs muted")
                    ui.label(f"수량 {float(p['quantity']):,.2f}").classes("text-sm muted mt-3")
                    if p["market"] == "KR":
                        ui.label(f"평단 ₩{float(p['average_price']):,.0f} · KRW").classes("text-sm muted")
                        if row.get("priced"):
                            ui.label(f"현재 ₩{row['current']:,.0f}").classes("text-xl font-black main-text")
                            local_rate = row["local_pnl"] / row["local_cost"] * 100 if row["local_cost"] else 0
                            ui.label(
                                f"손익 ₩{row['local_pnl']:+,.0f} ({local_rate:+.2f}%)"
                            ).classes(f"text-sm font-bold {delta_class(row['local_pnl'])}")
                        else:
                            ui.label("현재가 조회 실패").classes("text-xl font-black negative")
                            ui.label("총 평가손익 계산에서 제외").classes("text-xs muted")
                    else:
                        ui.label(f"평단 ${float(p['average_price']):,.2f} · USD").classes("text-sm muted")
                        if row.get("priced"):
                            ui.label(f"현재 ${row['current']:,.2f}").classes("text-xl font-black main-text")
                            local_rate = row["local_pnl"] / row["local_cost"] * 100 if row["local_cost"] else 0
                            ui.label(
                                f"손익 ${row['local_pnl']:+,.2f} ({local_rate:+.2f}%)"
                            ).classes(f"text-sm font-bold {delta_class(row['local_pnl'])}")
                            ui.label(
                                f"기준환율 {float(usdkrw):,.2f} KRW/USD · {base_currency['value']} 환산 {money_text_from_krw(row['value_krw'])}"
                            ).classes("text-xs muted")
                        else:
                            ui.label("현재가 조회 실패").classes("text-xl font-black negative")
                            ui.label("총 평가손익 계산에서 제외").classes("text-xs muted")

                    item = {
                        "symbol": p["symbol"], "name": p["name"],
                        "market": p["market"], "exchange": p["exchange"],
                    }
                    ui.button("수량·평단 수정", on_click=lambda current=item, existing=p: edit_position(current, existing)).props(
                        "flat dense no-caps"
                    ).classes("mt-2")

        with allocation_host:
            ui.label(f"자산 배분 · {base_currency['value']} 기준").classes("font-bold main-text")
            if valuation_rows and value > 0:
                data = [
                    {
                        "name": r["position"]["name"],
                        "value": round(base_amount(r["value_krw"]), 2),
                    }
                    for r in valuation_rows
                    if r.get("value_krw") is not None and r["value_krw"] > 0
                ]
                ui.echart({
                    "animation": False,
                    "tooltip": {"trigger": "item"},
                    "legend": {"bottom": 0, "textStyle": {"color": "#64748b"}},
                    "series": [{
                        "type": "pie",
                        "radius": ["48%", "72%"],
                        "center": ["50%", "43%"],
                        "label": {"show": False},
                        "data": data,
                    }],
                }).classes("w-full h-[260px]")
            else:
                ui.label("포지션을 등록하면 구성비가 표시됩니다.").classes("muted mt-4")

    await render_portfolio()

    with lab_host:
        ui.label("PORTFOLIO LAB").classes("section-title")
        ui.label(
            "목표비중, 드리프트, 매도 없는 리밸런싱, 백테스트, X-Ray, What-if, Stress Test"
        ).classes("text-xs muted")
        lab_content = ui.column().classes("w-full mt-3")

    async def save_all_targets(mode):
        nonlocal targets
        if not valuation_rows:
            return
        total_value = sum(float(r.get("value_krw") or 0) for r in valuation_rows)
        count = len(valuation_rows)
        saved = []
        for row in valuation_rows:
            item = row["position"]
            if mode == "equal":
                weight = 100 / count if count else 0
            else:
                weight = float(row.get("value_krw") or 0) / total_value * 100 if total_value else 0
            saved.append(
                await asyncio.to_thread(
                    upsert_target_allocation,
                    app.storage.user,
                    item,
                    weight,
                )
            )
        targets[:] = saved
        await render_lab()

    async def render_lab():
        lab_content.clear()
        with lab_content:
            if not valuation_rows:
                with ui.card().classes("surface p-7"):
                    ui.label("Portfolio Lab은 포트폴리오 포지션을 등록한 뒤 사용할 수 있습니다.").classes("muted")
                return

            current_values = {
                (r["position"]["market"], r["position"]["exchange"], r["position"]["symbol"]): float(r.get("value_krw") or 0)
                for r in valuation_rows
            }
            drift_rows, drift_score = drift_analysis(portfolio, targets, current_values)
            target_sum = sum(float(t.get("target_weight") or 0) for t in targets)
            threshold_pct = float(rebalance_rule.get("threshold_pct") or 5)
            alerts = [r for r in drift_rows if abs(r["drift"] * 100) >= threshold_pct]

            if rebalance_rule.get("enabled", True) and alerts:
                with ui.card().classes("surface p-4 w-full border-l-4 border-orange-400"):
                    ui.label(f"리밸런싱 알림 · {len(alerts)}개 종목이 ±{threshold_pct:.1f}%p 범위를 벗어났습니다.").classes(
                        "font-bold main-text"
                    )
                    ui.label(
                        " · ".join(f"{r['name']} {r['drift']*100:+.1f}%p" for r in alerts[:4])
                    ).classes("text-xs muted")

            with ui.grid(columns=4).classes("w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1"):
                for label, value, note in [
                    ("Rebalance Need", f"{drift_score:.0f}/100", "높을수록 목표에서 멀어짐"),
                    ("목표비중 합계", f"{target_sum:.1f}%", "100% 권장"),
                    ("허용 Drift", f"±{threshold_pct:.1f}%p", "초과 시 인앱 알림"),
                    ("Portfolio X-Ray", "분석 가능", "집중도·상관관계"),
                ]:
                    with ui.card().classes("surface p-4"):
                        ui.label(label).classes("text-xs font-bold muted")
                        ui.label(value).classes("text-xl font-black main-text mt-1")
                        ui.label(note).classes("text-xs muted")

            with ui.row().classes("w-full gap-2 mt-4"):
                ui.button("현재비중을 목표로", on_click=lambda: save_all_targets("current")).props("outline no-caps")
                ui.button("균등 1/N 목표", on_click=lambda: save_all_targets("equal")).props("outline no-caps")

            ui.label("목표 비중 & Drift").classes("font-bold main-text mt-5")
            with ui.grid(columns=2).classes("w-full gap-3 mt-2 max-md:grid-cols-1"):
                target_map = {
                    (t["market"], t["exchange"], t["symbol"]): t
                    for t in targets
                }
                for row in drift_rows:
                    target = target_map.get(row["key"])
                    with ui.card().classes("surface p-4"):
                        with ui.row().classes("w-full justify-between"):
                            ui.label(row["name"]).classes("font-bold main-text")
                            ui.label(f"Drift {row['drift']*100:+.1f}%p").classes(
                                f"text-sm font-bold {delta_class(-abs(row['drift'])) if abs(row['drift']) > .05 else 'muted'}"
                            )
                        ui.label(
                            f"현재 {row['current_weight']*100:.1f}% · 목표 {row['target_weight']*100:.1f}%"
                        ).classes("text-sm muted")
                        ui.label(
                            ("매수 " if row["trade_amount"] >= 0 else "매도 ")
                            + f"₩{abs(row['trade_amount']):,.0f}"
                        ).classes("text-sm main-text mt-1")

                        weight_input = ui.number(
                            "목표 %",
                            value=float((target or {}).get("target_weight") or 0),
                            min=0,
                            max=100,
                            step=0.5,
                        ).props("outlined dense").classes("w-32 mt-2")

                        async def save_target(current=row, field=weight_input):
                            nonlocal targets
                            item = next(
                                p for p in portfolio
                                if (p["market"], p["exchange"], p["symbol"]) == current["key"]
                            )
                            saved = await asyncio.to_thread(
                                upsert_target_allocation,
                                app.storage.user,
                                item,
                                field.value or 0,
                            )
                            index = next(
                                (
                                    i for i, t in enumerate(targets)
                                    if (t["market"], t["exchange"], t["symbol"]) == current["key"]
                                ),
                                None,
                            )
                            if index is None:
                                targets.append(saved)
                            else:
                                targets[index] = saved
                            await render_lab()

                        ui.button("저장", on_click=save_target).props("flat dense no-caps")

            with ui.card().classes("surface p-5 w-full mt-4"):
                ui.label("리밸런싱 알림 기준").classes("font-bold main-text")
                with ui.row().classes("items-end gap-3 mt-2"):
                    threshold = ui.number(
                        "허용 Drift (%p)",
                        value=threshold_pct,
                        min=1,
                        max=50,
                        step=0.5,
                    ).props("outlined dense").classes("w-40")
                    enabled = ui.switch(
                        "인앱 알림",
                        value=bool(rebalance_rule.get("enabled", True)),
                    )

                    async def save_rule():
                        saved = await asyncio.to_thread(
                            upsert_rebalance_rule,
                            app.storage.user,
                            threshold.value or 5,
                            enabled.value,
                        )
                        rebalance_rule.update(saved)
                        await render_lab()

                    ui.button("기준 저장", on_click=save_rule).props("unelevated no-caps").classes("primary")

            with ui.card().classes("surface p-5 w-full mt-4"):
                ui.label("Smart Rebalance · 매도 없이 균형 맞추기").classes("font-bold main-text")
                ui.label("추가 투자금을 과소비중 종목에 우선 배분합니다.").classes("text-xs muted")
                contribution = ui.number(
                    "추가 투자금 (원)", value=1_000_000, min=0, step=100_000
                ).props("outlined").classes("w-full max-w-sm mt-3")
                suggestion_host = ui.column().classes("w-full mt-3")

                async def suggest():
                    suggestion_host.clear()
                    suggestions = contribution_rebalance(drift_rows, contribution.value or 0)
                    with suggestion_host:
                        if not suggestions:
                            ui.label("추가 매수로 조정할 과소비중 종목이 없습니다.").classes("muted")
                        for suggestion in suggestions:
                            with ui.row().classes("w-full justify-between py-1"):
                                ui.label(suggestion["name"]).classes("main-text")
                                ui.label(f"₩{suggestion['contribution_amount']:,.0f} 매수").classes("font-bold main-text")

                ui.button("배분 계산", icon="calculate", on_click=suggest).props("outline no-caps").classes("mt-2")

            target_weights = {
                t["symbol"]: float(t.get("target_weight") or 0) / 100
                for t in targets
                if float(t.get("target_weight") or 0) > 0
            }
            if not target_weights:
                total_current = sum(current_values.values()) or 1
                target_weights = {
                    p["symbol"]: current_values.get((p["market"], p["exchange"], p["symbol"]), 0) / total_current
                    for p in portfolio
                }

            with ui.card().classes("surface p-5 w-full mt-4"):
                ui.label("리밸런싱 백테스트").classes("font-bold main-text")
                ui.label("리밸런싱 없음 / 매월 / 분기 / 연 1회 / ±5%p를 동일 목표비중으로 비교합니다.").classes("text-xs muted")
                backtest_host = ui.column().classes("w-full mt-3")

                async def run_backtest_ui():
                    backtest_host.clear()
                    with backtest_host:
                        ui.spinner(size="md")
                    tests = await asyncio.to_thread(
                        compare_rebalance_strategies,
                        portfolio,
                        target_weights,
                        "5y",
                    )
                    backtest_host.clear()
                    with backtest_host:
                        with ui.grid(columns=5).classes("w-full gap-2 max-lg:grid-cols-2"):
                            for test in tests:
                                m = test["metrics"]
                                with ui.card().classes("surface p-3"):
                                    ui.label(test["label"]).classes("text-xs font-bold muted")
                                    ui.label(f"CAGR {m.cagr*100:.1f}%").classes("font-bold main-text")
                                    ui.label(f"MDD {m.max_drawdown*100:.1f}%").classes("text-xs muted")
                                    ui.label(f"Sharpe {m.sharpe:.2f}").classes("text-xs muted")
                        series = []
                        dates = []
                        for test in tests:
                            if test["dates"] and not dates:
                                dates = test["dates"]
                            series.append({
                                "name": test["label"],
                                "type": "line",
                                "data": [round(v * 100, 2) for v in test["equity"]],
                                "showSymbol": False,
                                "lineStyle": {"width": 1.6},
                            })
                        if dates:
                            ui.echart({
                                "animation": False,
                                "tooltip": {"trigger": "axis"},
                                "legend": {"top": 0, "textStyle": {"color": "#64748b"}},
                                "grid": {"left": 55, "right": 18, "top": 45, "bottom": 45},
                                "xAxis": {"type": "category", "data": dates, "axisLabel": {"hideOverlap": True}},
                                "yAxis": {"type": "value", "name": "초기 100"},
                                "dataZoom": [{"type": "inside"}],
                                "series": series,
                            }).classes("w-full h-[420px] mt-3")

                ui.button("5년 백테스트 실행", icon="science", on_click=run_backtest_ui).props("outline no-caps").classes("mt-2")

            with ui.card().classes("surface p-5 w-full mt-4"):
                ui.label("Drift Timeline").classes("font-bold main-text")
                ui.label("목표비중으로 시작했다고 가정할 때 시간이 지나며 비중이 얼마나 틀어졌는지 봅니다.").classes("text-xs muted")
                drift_timeline_host = ui.column().classes("w-full mt-2")

                async def run_drift_timeline():
                    drift_timeline_host.clear()
                    with drift_timeline_host:
                        ui.spinner(size="md")
                    timeline = await asyncio.to_thread(
                        drift_timeline, portfolio, target_weights, "2y"
                    )
                    drift_timeline_host.clear()
                    with drift_timeline_host:
                        if not timeline["dates"]:
                            ui.label("표시할 데이터가 없습니다.").classes("muted")
                            return
                        ui.echart({
                            "animation": False,
                            "tooltip": {"trigger": "axis"},
                            "grid": {"left": 55, "right": 18, "top": 20, "bottom": 45},
                            "xAxis": {"type": "category", "data": timeline["dates"], "axisLabel": {"hideOverlap": True}},
                            "yAxis": {"type": "value", "name": "Drift %"},
                            "dataZoom": [{"type": "inside"}],
                            "series": [{
                                "type": "line",
                                "data": timeline["drift"],
                                "showSymbol": False,
                                "lineStyle": {"width": 2, "color": "#f59e0b"},
                                "areaStyle": {"color": "rgba(245,158,11,.10)"},
                            }],
                        }).classes("w-full h-[300px]")

                ui.button("2년 Drift 보기", on_click=run_drift_timeline).props("outline no-caps").classes("mt-2")

            with ui.grid(columns=2).classes("w-full gap-4 mt-4 max-lg:grid-cols-1"):
                with ui.card().classes("surface p-5"):
                    ui.label("Portfolio X-Ray").classes("font-bold main-text")
                    ui.label("집중도·유효 종목수·평균 상관관계를 진단합니다.").classes("text-xs muted")
                    xray_host = ui.column().classes("w-full mt-3")

                    async def run_xray():
                        xray_host.clear()
                        with xray_host:
                            ui.spinner(size="md")
                        result = await asyncio.to_thread(xray, portfolio, target_weights, "2y")
                        xray_host.clear()
                        with xray_host:
                            ui.label(f"Portfolio Score {result['score']} / 100").classes("text-2xl font-black main-text")
                            ui.label(f"상위 1종목 {result['top_weight']*100:.1f}% · 유효 종목수 {result['effective_n']:.1f}").classes("text-sm muted")
                            ui.label(f"평균 상관계수 {result['avg_corr']:.2f}").classes("text-sm muted")
                            ui.echart({
                                "animation": False,
                                "series": [{
                                    "type": "pie",
                                    "radius": ["45%", "70%"],
                                    "data": [
                                        {"name": "한국", "value": round(result["region"].get("KR", 0)*100, 2)},
                                        {"name": "미국", "value": round(result["region"].get("US", 0)*100, 2)},
                                    ],
                                }],
                                "legend": {"bottom": 0},
                            }).classes("w-full h-[220px]")

                    ui.button("X-Ray 실행", on_click=run_xray).props("outline no-caps").classes("mt-2")

                with ui.card().classes("surface p-5"):
                    ui.label("What-if Simulator").classes("font-bold main-text")
                    ui.label("한 종목의 목표비중을 바꾸면 과거 위험지표가 어떻게 달라졌는지 봅니다.").classes("text-xs muted")
                    options = {p["symbol"]: p["name"] for p in portfolio}
                    selected = ui.select(options=options, value=portfolio[0]["symbol"], label="종목").props("outlined").classes("w-full mt-3")
                    new_weight = ui.number("새 목표비중 %", value=20, min=0, max=100, step=1).props("outlined").classes("w-full")
                    whatif_host = ui.column().classes("w-full mt-2")

                    async def run_whatif():
                        result = await asyncio.to_thread(
                            what_if,
                            portfolio,
                            target_weights,
                            selected.value,
                            (new_weight.value or 0) / 100,
                            "2y",
                        )
                        whatif_host.clear()
                        with whatif_host:
                            if not result:
                                ui.label("계산할 수 없습니다.").classes("muted")
                                return
                            base = result["base"]
                            new = result["new"]
                            ui.label(
                                f"변동성 {base.volatility*100:.1f}% → {new.volatility*100:.1f}%"
                            ).classes("font-bold main-text")
                            ui.label(
                                f"MDD {base.max_drawdown*100:.1f}% → {new.max_drawdown*100:.1f}%"
                            ).classes("text-sm muted")
                            ui.label(
                                f"Sharpe {base.sharpe:.2f} → {new.sharpe:.2f}"
                            ).classes("text-sm muted")

                    ui.button("What-if 계산", on_click=run_whatif).props("outline no-caps").classes("mt-2")

            ui.label("Stress Test").classes("font-bold main-text mt-5")
            with ui.grid(columns=4).classes("w-full gap-3 mt-2 max-md:grid-cols-2"):
                for scenario in stress_tests(portfolio, target_weights):
                    with ui.card().classes("surface p-4"):
                        ui.label(scenario["name"]).classes("text-xs font-bold muted")
                        ui.label(f"{scenario['shock']*100:.1f}%").classes("text-xl font-black negative mt-1")
                        current_total = sum(current_values.values())
                        ui.label(f"약 {current_total*scenario['shock']:+,.0f}원").classes("text-xs muted")

    await render_lab()

    with macro_host:
        ui.label("Market Center").classes("section-title")
        ui.label("경제지표·선물·환율·한국/미국 금리곡선을 분리해 봅니다.").classes("text-xs muted")
        with ui.tabs().classes("w-full dashboard-tabs mt-3") as market_tabs:
            macro_tab = ui.tab("경제지표", icon="insights")
            futures_tab2 = ui.tab("선물", icon="candlestick_chart")
            fx_tab2 = ui.tab("환율", icon="currency_exchange")
            bonds_tab2 = ui.tab("채권", icon="timeline")
            heatmap_tab2 = ui.tab("히트맵", icon="grid_view")
        with ui.tab_panels(market_tabs, value=macro_tab).classes("w-full bg-transparent"):
            with ui.tab_panel(macro_tab).classes("p-0"):
                macro_grid2 = ui.grid(columns=4).classes("w-full gap-3 mt-3 max-md:grid-cols-2")
            with ui.tab_panel(futures_tab2).classes("p-0"):
                futures_grid2 = ui.grid(columns=4).classes("w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1")
            with ui.tab_panel(fx_tab2).classes("p-0"):
                fx_grid2 = ui.grid(columns=4).classes("w-full gap-3 mt-3 max-lg:grid-cols-2 max-md:grid-cols-1")
            with ui.tab_panel(bonds_tab2).classes("p-0"):
                bonds_host2 = ui.column().classes("w-full mt-3 gap-4")
            with ui.tab_panel(heatmap_tab2).classes("p-0"):
                heatmap_host2 = ui.column().classes("w-full mt-3 gap-4")

        with macro_grid2:
            for item in macro:
                with ui.card().classes("surface market-card p-4") as card:
                    async def open_macro(current=item):
                        ui.navigate.to(f"/indicator/macro/{quote(current['id'], safe='')}")
                    card.on("click", open_macro)
                    ui.label(item["name"]).classes("text-xs font-bold muted")
                    ui.label("-" if item["value"] is None else f"{item['value']:.2f}{item['suffix']}").classes("text-xl font-black main-text")
                    svg = mini_svg(item.get("spark") or [], height=38)
                    if svg:
                        ui.html(svg).classes("w-full mt-2")

        async def render_market_center():
            keys = ["futures", "fx", "us_curve", "kr_curve", "us_heat", "kr_heat"]
            missing = [k for k in keys if engine.get(k) is None]
            if missing:
                await asyncio.gather(*(engine.refresh(k) for k in missing))
            futures = engine.get("futures", [])
            fx = engine.get("fx", [])
            us_curve = engine.get("us_curve", [])
            kr_curve = engine.get("kr_curve", [])
            us_heat = engine.get("us_heat", [])
            kr_heat = engine.get("kr_heat", [])
            futures_grid2.clear()
            with futures_grid2:
                for item in futures:
                    with ui.card().classes("surface p-4"):
                        ui.label(item["name"]).classes("text-xs font-bold muted")
                        ui.label("-" if item.get("value") is None else f"{item['value']:,.2f}").classes("text-xl font-black main-text")
                        pct=item.get("percent")
                        if pct is not None:
                            ui.label(f"{pct:+.2f}%").classes(f"text-xs font-bold {delta_class(pct)}")
                        svg=mini_svg(item.get("spark") or [], height=34)
                        if svg: ui.html(svg).classes("w-full mt-2")
            fx_grid2.clear()
            with fx_grid2:
                for item in fx:
                    with ui.card().classes("surface p-4"):
                        ui.label(item["name"]).classes("text-xs font-bold muted")
                        value=item.get("value")
                        text_value = "-" if value is None else (f"{value:,.4f}" if abs(value)<100 else f"{value:,.2f}")
                        ui.label(text_value).classes("text-xl font-black main-text")
                        pct=item.get("percent")
                        if pct is not None: ui.label(f"{pct:+.2f}%").classes(f"text-xs font-bold {delta_class(pct)}")
            await render_bond_panel(bonds_host2, us_curve, kr_curve)
            heatmap_host2.clear()
            with heatmap_host2:
                with ui.tabs().classes('w-full dashboard-tabs') as personal_hm_tabs:
                    ph_us=ui.tab('미국')
                    ph_kr=ui.tab('한국')
                with ui.tab_panels(personal_hm_tabs, value=ph_us).classes('w-full bg-transparent'):
                    with ui.tab_panel(ph_us).classes('p-0'):
                        ui.echart(echart_treemap(us_heat, 'US Large Cap Heatmap'), renderer='canvas').classes('w-full h-[520px] surface')
                    with ui.tab_panel(ph_kr).classes('p-0'):
                        if kr_heat:
                            ui.echart(echart_treemap(kr_heat, 'Korea Market Cap Heatmap'), renderer='canvas').classes('w-full h-[520px] surface')
                        else:
                            ui.label('한국 히트맵 데이터를 불러오지 못했습니다.').classes('muted p-5')
            if not os.getenv('ECOS_API_KEY'):
                with bonds_host2:
                    ui.label("한국 국고채 다만기 데이터는 ECOS_API_KEY 설정을 권장합니다. sample 키는 호출 제한이 큽니다.").classes("text-xs muted")

        asyncio.create_task(render_market_center())

    with news_host:
        with ui.row().classes("w-full items-end justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("뉴스").classes("section-title")
                ui.label(
                    "관심종목 뉴스를 Yahoo Finance와 NAVER 검색 API에서 모읍니다."
                ).classes("text-xs muted")
            news_source = ui.toggle(
                {"ALL": "통합", "NAVER": "네이버", "YAHOO": "Yahoo"},
                value="ALL",
            ).props("unelevated")
        news_list = ui.column().classes("w-full surface px-5 mt-3")

    news_cache = {"all": [], "naver": [], "yahoo": []}

    async def fetch_news_sources():
        yahoo, naver = await asyncio.gather(
            asyncio.to_thread(get_watchlist_news, watchlist, 12),
            asyncio.to_thread(get_naver_news_for_watchlist, watchlist, 3, 12),
        )
        for item in yahoo:
            item.setdefault("source_type", "YAHOO")
        news_cache["yahoo"] = yahoo
        news_cache["naver"] = naver
        news_cache["all"] = merge_news(yahoo, naver, 20)

    async def render_news():
        if not news_cache["all"] and not news_cache["yahoo"]:
            await fetch_news_sources()
        key = news_source.value.lower()
        data = news_cache.get(key, news_cache["all"])
        news_list.clear()
        with news_list:
            if news_source.value == "NAVER" and not naver_news_enabled():
                ui.label(
                    "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET을 Render 환경변수에 설정하면 네이버 뉴스가 표시됩니다."
                ).classes("py-5 muted")
                return
            if not data:
                ui.label("표시할 뉴스가 없습니다.").classes("py-5 muted")
                return
            for item in data:
                with ui.column().classes(
                    "w-full py-4 border-b border-[var(--border)] last:border-0 gap-1"
                ):
                    with ui.row().classes("w-full items-start justify-between gap-3 no-wrap"):
                        if item.get("url"):
                            ui.link(
                                item["title"], item["url"], new_tab=True
                            ).classes("main-text font-semibold no-underline")
                        else:
                            ui.label(item["title"]).classes("main-text font-semibold")
                        ui.label(item.get("source_type", "YAHOO")).classes(
                            "pill text-[10px] font-bold shrink-0"
                        )
                    ui.label(
                        " · ".join(
                            x for x in [item.get("symbol", ""), item.get("publisher", "")]
                            if x
                        )
                    ).classes("text-xs muted")

    news_source.on(
        "update:model-value",
        lambda _: render_news(),
        throttle=0.1,
        leading_events=False,
        trailing_events=True,
    )
    asyncio.create_task(render_news())



@ui.page(
    "/stock/{market}/{exchange}/{symbol}",
    response_timeout=15,
)
async def stock_detail(market: str, exchange: str, symbol: str):
    add_style()
    _, set_theme = apply_theme()

    with ui.row().classes("w-full items-center justify-between sticky top-0 z-10 py-3"):
        ui.button(
            "이전 화면", icon="arrow_back", on_click=lambda: ui.run_javascript("history.back()")
        ).props("flat no-caps")
        with ui.row().classes("gap-2"):
            theme_menu(set_theme)
            ui.button("시장 홈", icon="public", on_click=lambda: ui.navigate.to("/")).props("flat no-caps")
            if logged_in():
                ui.button(
                    "내 대시보드", icon="dashboard", on_click=lambda: ui.navigate.to("/dashboard")
                ).props("flat no-caps")

    name_label = ui.label(symbol).classes("text-3xl font-black main-text mt-5")
    ui.label(f"{symbol} · {exchange} · {market}").classes("text-sm muted")

    with ui.card().classes("surface p-5 mt-5"):
        price_label = ui.label("가격 불러오는 중...").classes("text-3xl font-black main-text")
        change_label = ui.label("-").classes("text-sm font-bold muted")

    extended_host = ui.row().classes("w-full gap-3 mt-3 flex-wrap")
    extended_refs = {}
    live_badge = ui.label("").classes("text-xs muted mt-1")

    with ui.row().classes("w-full items-center gap-3 mt-6"):
        timeframe = ui.toggle(
            {"1D": "1일", "D": "일봉", "W": "주봉", "M": "월봉"},
            value="D",
        ).props("unelevated")
        ma = ui.select(
            options={5: "MA5", 20: "MA20", 60: "MA60", 120: "MA120"},
            value=[5, 20, 60, 120],
            multiple=True,
            label="이동평균선",
        ).props("outlined use-chips dense").classes("w-full max-w-xl")

    status = ui.label("일봉 차트를 준비하고 있습니다...").classes("text-xs muted mt-2")
    chart = ui.echart({
        "animation": False,
        "xAxis": {"type": "category", "data": []},
        "yAxis": {"type": "value"},
        "series": [],
    }, renderer="canvas").classes("w-full h-[610px] chart-wrap mt-3")

    await ui.context.client.connected()

    try:
        found = await asyncio.to_thread(search_stocks, symbol)
        exact = next(
            (x for x in found if x["market"] == market and x["symbol"] == symbol),
            None,
        )
        if exact:
            name_label.set_text(exact["name"])
    except Exception:
        pass

    async def load_quote():
        try:
            q = (
                await asyncio.to_thread(kis.get_domestic_quote, symbol)
                if market == "KR"
                else await asyncio.to_thread(get_us_quote, symbol)
            )
            price, change, pct = q.get("price"), q.get("change"), q.get("change_percent")
            if q.get("currency") == "KRW":
                price_label.set_text("-" if price is None else f"{price:,.0f}원")
                change_label.set_text(
                    "-" if change is None or pct is None else f"{change:+,.0f}원 ({pct:+.2f}%)"
                )
            else:
                price_label.set_text("-" if price is None else f"${price:,.2f}")
                change_label.set_text(
                    "-" if change is None or pct is None else f"${change:+,.2f} ({pct:+.2f}%)"
                )
        except Exception as exc:
            price_label.set_text("조회 실패")
            change_label.set_text(str(exc)[:90])

    def render_extended_shell():
        extended_host.clear()
        extended_refs.clear()
        with extended_host:
            keys = (
                [('premarket','프리마켓'), ('regular','정규장'), ('afterhours','애프터마켓')]
                if market == 'US'
                else [('expected','장전/동시호가'), ('regular','정규장'), ('after','시간외 단일가')]
            )
            for key, label in keys:
                with ui.card().classes('surface px-4 py-3 min-w-[165px]'):
                    ui.label(label).classes('text-xs muted')
                    price = ui.label('-').classes('text-lg font-black main-text')
                    change = ui.label('').classes('text-xs muted')
                    extended_refs[key] = (price, change)
            session_ref = ui.label('세션 확인 중...').classes('text-xs muted self-center')
            extended_refs['session'] = session_ref

    def refresh_extended_from_cache():
        if market != 'US' or not extended_refs:
            return
        snap = us_realtime.get(symbol)

        # Keep the headline synchronized with WS; use the batched fallback when WS is stale.
        display_last = snap.get('display_last')
        if display_last is not None:
            price_label.set_text(f"${float(display_last):,.2f}")
            live_change = snap.get('display_change')
            live_pct = snap.get('display_percent')
            prefix = {'LIVE': 'TRADE LIVE', 'QUOTE': 'QUOTE LIVE'}.get(snap.get('state'), 'SNAPSHOT')
            change_label.set_text(
                prefix if live_change is None or live_pct is None
                else f"${float(live_change):+,.2f} ({float(live_pct):+.2f}%) · {prefix}"
            )

        for key in ('premarket','regular','afterhours'):
            price_label, delta_label = extended_refs[key]
            value = snap.get(key)
            price_label.set_text('-' if value is None else f'${value:,.2f}')
            if snap.get('live') and snap.get('session') == {'premarket':'PRE','regular':'REGULAR','afterhours':'POST'}[key]:
                pct = snap.get('percent')
                change = snap.get('change')
                delta_label.set_text('LIVE' if pct is None else f'{change:+.2f} ({pct:+.2f}%)')
                delta_label.classes(remove='muted positive negative')
                delta_label.classes(add='positive' if (pct or 0) > 0 else 'negative' if (pct or 0) < 0 else 'muted')
            else:
                delta_label.set_text('')
        session = snap.get('session','CLOSED')
        source_map = {
            'LIVE': 'KIS TRADE LIVE',
            'QUOTE': 'KIS QUOTE LIVE',
            'SNAPSHOT': '3~5s SNAPSHOT',
            'ACKED': 'KIS WS READY',
            'ERROR': 'SNAPSHOT 사용중',
            'SUBSCRIBING': '시세 준비중',
        }
        source = source_map.get(snap.get('state'), snap.get('source','POLL'))
        extended_refs['session'].set_text(f'현재 세션: {session} · {source}')

    def refresh_kr_extended_from_cache():
        if market != 'KR' or not extended_refs:
            return
        snap = kr_realtime.get(symbol)
        value = snap.get('display_last')
        pct = snap.get('display_percent')
        change = snap.get('display_change')
        if value is not None:
            price_label.set_text(f'{float(value):,.0f}원')
            state_text = 'LIVE' if snap.get('state') == 'LIVE' else 'SNAPSHOT'
            change_label.set_text(
                state_text if change is None or pct is None
                else f'{float(change):+,.0f}원 ({float(pct):+.2f}%) · {state_text}'
            )
        for key in ('expected','regular','after'):
            p_label, d_label = extended_refs[key]
            v = snap.get(key)
            p_label.set_text('-' if v is None else f'{float(v):,.0f}원')
            d_label.set_text('LIVE' if snap.get('live') and (
                (key == 'expected' and snap.get('session') in ('PRE','CLOSING')) or
                (key == 'regular' and snap.get('session') == 'REGULAR') or
                (key == 'after' and snap.get('session') == 'AFTER')
            ) else '')
        session = snap.get('session', 'CLOSED')
        names = {'PRE':'장전 예상체결','REGULAR':'정규장','CLOSING':'장마감 동시호가','AFTER':'시간외 단일가','CLOSED':'마감'}
        extended_refs['session'].set_text(f"현재 세션: {names.get(session, session)} · KIS {snap.get('state','SNAPSHOT')}")

    async def load_extended_hours():
        if market == 'US':
            try:
                batch = await asyncio.to_thread(get_us_extended_batch, [(symbol, exchange)])
                if batch.get(symbol):
                    us_realtime.seed_extended(symbol, batch[symbol])
                else:
                    polled = await asyncio.to_thread(get_us_extended_session, symbol)
                    us_realtime.seed_extended(symbol, polled)
            except Exception:
                pass
            try:
                await us_realtime.subscribe(symbol, exchange)
            except Exception:
                pass
            refresh_extended_from_cache()
        else:
            try:
                q = await asyncio.to_thread(kis.get_domestic_quote, symbol)
                kr_realtime.seed(symbol, q.get('price'), q.get('change_percent'), q.get('change'))
            except Exception:
                pass
            try:
                await kr_realtime.subscribe(symbol)
            except Exception:
                pass
            refresh_kr_extended_from_cache()

    chart_lock = asyncio.Lock()

    async def load_chart():
        if chart_lock.locked():
            return
        async with chart_lock:
            status.set_text(f"{timeframe.value} 데이터를 불러오는 중...")
            try:
                options = await asyncio.to_thread(
                    get_echart_options,
                    kis,
                    market,
                    exchange,
                    symbol,
                    timeframe.value,
                    tuple(ma.value or []),
                )
                chart.options.clear()
                chart.options.update(options)
                chart.update()
                status.set_text("마우스 휠/드래그로 확대·축소할 수 있습니다.")
            except Exception as exc:
                status.set_text(f"차트 조회 실패: {exc}")

    timeframe.on(
        "update:model-value",
        lambda _: load_chart(),
        throttle=0.15,
        leading_events=False,
        trailing_events=True,
    )
    ma.on(
        "update:model-value",
        lambda _: load_chart(),
        throttle=0.15,
        leading_events=False,
        trailing_events=True,
    )

    render_extended_shell()
    await asyncio.gather(load_quote(), load_extended_hours(), load_chart())
    ui.timer(REFRESH_SECONDS, load_quote)
    ui.timer(1.0, lambda: refresh_extended_from_cache() if market == 'US' else refresh_kr_extended_from_cache())
    if market == 'US':
        ui.timer(15.0, load_extended_hours)



@ui.page('/bond/{country}/{tenor}', response_timeout=15)
async def bond_detail(country: str, tenor: str):
    add_style()
    _, set_theme = apply_theme()
    with ui.row().classes('w-full items-center justify-between'):
        ui.button('이전 화면', icon='arrow_back', on_click=lambda: ui.run_javascript('history.back()')).props('flat no-caps')
        with ui.row().classes('items-center gap-2'):
            theme_menu(set_theme)
            ui.button('시장 홈', icon='public', on_click=lambda: ui.navigate.to('/')).props('flat no-caps')

    is_spread = country == 'spread'
    title_text = (
        f'US {tenor} Treasury Yield' if country == 'us'
        else f'한국 국고채 {tenor}' if country == 'kr'
        else f'한국 Yield Spread {tenor.replace("KR-", "")}' if tenor.startswith('KR-')
        else f'US Yield Spread {tenor}'
    )
    ui.label(title_text).classes('text-3xl font-black main-text mt-5')
    ui.label('만기별 금리의 역사적 흐름을 확인합니다.').classes('text-sm muted')
    years = ui.toggle({1:'1년',3:'3년',5:'5년',10:'10년'}, value=5).props('unelevated').classes('mt-5')
    status = ui.label('금리 데이터를 준비하고 있습니다...').classes('text-xs muted mt-2')
    chart = ui.echart({'animation':False,'xAxis':{'type':'category','data':[]},'yAxis':{'type':'value'},'series':[]}, renderer='canvas').classes('w-full h-[560px] chart-wrap mt-3')
    await ui.context.client.connected()

    async def load_bond_chart():
        status.set_text('데이터를 불러오는 중...')
        try:
            if country == 'us':
                frame = await asyncio.to_thread(get_us_bond_history, tenor, int(years.value))
                chart_title = f'US Treasury {tenor}'
            elif country == 'kr':
                frame = await asyncio.to_thread(get_kr_bond_history, tenor, int(years.value))
                chart_title = f'Korea Treasury {tenor}'
            elif tenor.startswith('KR-'):
                clean_tenor = tenor.replace('KR-', '', 1)
                frame = await asyncio.to_thread(get_kr_spread_history, clean_tenor, int(years.value))
                chart_title = f'Korea Spread {clean_tenor}'
            else:
                frame = await asyncio.to_thread(get_us_spread_history, tenor, int(years.value))
                chart_title = f'US Spread {tenor}'
            options = line_chart_options(frame, chart_title)
            if not options:
                raise RuntimeError('표시할 금리 데이터가 없습니다.')
            chart.options.clear()
            chart.options.update(options)
            chart.update()
            status.set_text('마우스 휠/드래그로 구간을 확대할 수 있습니다.')
        except Exception as exc:
            status.set_text(f'금리 차트 조회 실패: {exc}')

    years.on('update:model-value', lambda _: load_bond_chart(), throttle=.2, leading_events=False, trailing_events=True)
    await load_bond_chart()


@ui.page("/indicator/{kind}/{code}", response_timeout=15)
async def indicator_detail(kind: str, code: str):
    add_style()
    _, set_theme = apply_theme()

    with ui.row().classes("w-full items-center justify-between"):
        ui.button(
            "이전 화면", icon="arrow_back", on_click=lambda: ui.run_javascript("history.back()")
        ).props("flat no-caps")
        with ui.row().classes("items-center gap-2"):
            theme_menu(set_theme)
            ui.button("시장 홈", icon="public", on_click=lambda: ui.navigate.to("/")).props("flat no-caps")

    title = ui.label(
        MARKET_LABELS.get(code, code) if kind == "market" else MACRO_LABELS.get(code, code)
    ).classes("text-3xl font-black main-text mt-5")
    ui.label("시장 가격 시계열" if kind == "market" else "FRED 공식 경제 시계열").classes("text-sm muted")

    ranges = ui.toggle(
        {"1M": "1개월", "3M": "3개월", "1Y": "1년", "5Y": "5년", "10Y": "10년"},
        value="1Y",
    ).props("unelevated").classes("mt-5")
    status = ui.label("차트 준비 중...").classes("text-xs muted mt-2")
    chart = ui.echart({
        "animation": False,
        "xAxis": {"type": "category", "data": []},
        "yAxis": {"type": "value"},
        "series": [],
    }, renderer="canvas").classes("w-full h-[540px] chart-wrap mt-3")

    await ui.context.client.connected()
    lock = asyncio.Lock()

    async def render():
        if lock.locked():
            return
        async with lock:
            status.set_text("데이터를 불러오는 중...")
            try:
                resolved_title, options = await asyncio.to_thread(
                    make_indicator_options, kind, code, ranges.value
                )
                title.set_text(resolved_title)
                chart.options.clear()
                chart.options.update(options)
                chart.update()
                status.set_text("드래그/휠로 구간을 확대할 수 있습니다.")
            except Exception as exc:
                status.set_text(f"지표 차트 조회 실패: {exc}")

    ranges.on(
        "update:model-value",
        lambda _: render(),
        throttle=0.15,
        leading_events=False,
        trailing_events=True,
    )
    await render()


@app.get("/diagnostics")
def diagnostics():
    return {
        "realtime": us_realtime.diagnostics(),
        "kr_realtime": kr_realtime.diagnostics(),
        "ecos": get_ecos_diagnostics(),
        "cache": {
            key: engine.meta(key)
            for key in (
                "markets", "macro", "futures", "fx",
                "us_curve", "kr_curve", "us_heat", "kr_heat"
            )
        },
    }


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
