import asyncio

from nicegui import ui

from global_market_data import (
    curve_compare_options,
    get_kr_curve_snapshots,
    get_kr_spread_history,
    get_kr_yield_curve,
    get_us_curve_snapshots,
    get_us_spread_history,
    get_us_yield_curve,
    line_chart_options,
)


def _current_curve_options(curve, title):
    categories = [x.get("tenor") for x in curve]
    values = [x.get("value") for x in curve]
    return {
        "animation": False,
        "backgroundColor": "transparent",
        "title": {
            "text": title,
            "left": 12,
            "top": 8,
            "textStyle": {"color": "#e2e8f0", "fontSize": 14},
        },
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 48, "right": 15, "top": 48, "bottom": 36},
        "xAxis": {
            "type": "category",
            "data": categories,
            "axisLabel": {"color": "#94a3b8"},
        },
        "yAxis": {
            "type": "value",
            "scale": True,
            "axisLabel": {"formatter": "{value}%", "color": "#94a3b8"},
            "splitLine": {"lineStyle": {"color": "rgba(100,116,139,.13)"}},
        },
        "series": [
            {
                "type": "line",
                "data": values,
                "smooth": True,
                "symbolSize": 7,
                "connectNulls": False,
            }
        ],
    }


async def render_bond_panel(host, us_curve=None, kr_curve=None):
    """Render current curves, historical curve snapshots and spread previews."""
    if us_curve is None or kr_curve is None:
        us_curve, kr_curve = await asyncio.gather(
            asyncio.to_thread(get_us_yield_curve),
            asyncio.to_thread(get_kr_yield_curve),
        )

    host.clear()
    with host:
        with ui.tabs().classes("w-full dashboard-tabs") as tabs:
            current_tab = ui.tab("현재 YC", icon="timeline")
            history_tab = ui.tab("YC 변화", icon="history")
            spread_tab = ui.tab("스프레드", icon="show_chart")

        with ui.tab_panels(tabs, value=current_tab).classes("w-full bg-transparent"):
            with ui.tab_panel(current_tab).classes("p-0 pt-3"):
                with ui.grid(columns=2).classes("w-full gap-4 max-md:grid-cols-1"):
                    for country, title, curve in [
                        ("us", "미국 국채 수익률", us_curve),
                        ("kr", "한국 국고채 수익률", kr_curve),
                    ]:
                        with ui.card().classes("surface p-5"):
                            ui.label(title).classes("font-bold main-text")
                            ui.label("만기 버튼을 누르면 해당 금리의 역사차트를 엽니다.").classes("text-xs muted")
                            ui.echart(
                                _current_curve_options(curve, title),
                                renderer="canvas",
                            ).classes("w-full h-[280px]")
                            with ui.row().classes("w-full gap-2 flex-wrap mt-2"):
                                for point in curve:
                                    tenor = point.get("tenor")
                                    value = point.get("value")
                                    button_text = tenor if value is None else f"{tenor} {value:.2f}%"
                                    ui.button(
                                        button_text,
                                        on_click=lambda _, c=country, t=tenor: ui.navigate.to(f"/bond/{c}/{t}"),
                                    ).props("outline dense no-caps").classes("text-xs")

            with ui.tab_panel(history_tab).classes("p-0 pt-3"):
                history_host = ui.column().classes("w-full gap-4")
                with history_host:
                    ui.spinner(size="md").classes("m-8 self-center")

            with ui.tab_panel(spread_tab).classes("p-0 pt-3"):
                spread_host = ui.column().classes("w-full gap-4")
                with spread_host:
                    ui.spinner(size="md").classes("m-8 self-center")

    async def load_history():
        us_snaps, kr_snaps = await asyncio.gather(
            asyncio.to_thread(get_us_curve_snapshots),
            asyncio.to_thread(get_kr_curve_snapshots),
        )
        history_host.clear()
        with history_host:
            ui.label("현재·1개월 전·3개월 전·1년 전 Yield Curve를 한 그래프에서 비교합니다.").classes("text-xs muted")
            with ui.grid(columns=2).classes("w-full gap-4 max-md:grid-cols-1"):
                for title, snaps in [
                    ("미국 Yield Curve 변화", us_snaps),
                    ("한국 Yield Curve 변화", kr_snaps),
                ]:
                    with ui.card().classes("surface p-4"):
                        options = curve_compare_options(snaps, title)
                        if options:
                            ui.echart(options, renderer="canvas").classes("w-full h-[360px]")
                        else:
                            ui.label("비교 데이터를 불러오지 못했습니다.").classes("muted p-5")

    async def load_spreads():
        us_spread, kr_spread = await asyncio.gather(
            asyncio.to_thread(get_us_spread_history, "10Y-2Y", 5),
            asyncio.to_thread(get_kr_spread_history, "10Y-2Y", 5),
        )
        spread_host.clear()
        with spread_host:
            with ui.grid(columns=2).classes("w-full gap-4 max-md:grid-cols-1"):
                for country, title, frame in [
                    ("us", "미국 10Y-2Y · 최근 5년", us_spread),
                    ("kr", "한국 10Y-2Y · 최근 5년", kr_spread),
                ]:
                    with ui.card().classes("surface p-4"):
                        opts = line_chart_options(frame, title, suffix="%p")
                        if opts:
                            ui.echart(opts, renderer="canvas").classes("w-full h-[300px]")
                            ui.button(
                                "상세 차트",
                                icon="open_in_full",
                                on_click=lambda _, c=country: ui.navigate.to(
                                    "/bond/spread/10Y-2Y" if c == "us" else "/bond/spread/KR-10Y-2Y"
                                ),
                            ).props("outline dense no-caps").classes("mt-2")
                        else:
                            ui.label("2년물 데이터가 확인되지 않아 스프레드를 계산하지 못했습니다.").classes("text-xs muted p-4")

    # Do not block the rest of the dashboard on historical bond downloads.
    asyncio.create_task(load_history())
    asyncio.create_task(load_spreads())
