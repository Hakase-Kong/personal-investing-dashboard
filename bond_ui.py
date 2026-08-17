import asyncio

from nicegui import ui

from global_market_data import (
    curve_at_date,
    curve_available_dates,
    get_kr_spread_history,
    get_us_spread_history,
    line_chart_options,
)


def _current_curve_options(curve, title, compare=None, compare_name="선택 시점"):
    categories = [x.get("tenor") for x in curve]
    series = [
        {
            "name": "현재",
            "type": "line",
            "data": [x.get("value") for x in curve],
            "smooth": True,
            "symbolSize": 7,
            "connectNulls": False,
            "lineStyle": {"width": 2.4},
        }
    ]
    if compare:
        values = {x.get("tenor"): x.get("value") for x in compare}
        series.append(
            {
                "name": compare_name,
                "type": "line",
                "data": [values.get(t) for t in categories],
                "smooth": True,
                "symbolSize": 6,
                "connectNulls": False,
                "lineStyle": {"width": 1.8, "type": "dashed"},
            }
        )
    return {
        "animation": False,
        "backgroundColor": "transparent",
        "title": {"text": title, "left": 12, "top": 8, "textStyle": {"color": "#e2e8f0", "fontSize": 14}},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 34, "textStyle": {"color": "#94a3b8"}},
        "grid": {"left": 48, "right": 15, "top": 72, "bottom": 36},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"color": "#94a3b8"}},
        "yAxis": {
            "type": "value",
            "scale": True,
            "axisLabel": {"formatter": "{value}%", "color": "#94a3b8"},
            "splitLine": {"lineStyle": {"color": "rgba(100,116,139,.13)"}},
        },
        "series": series,
    }


def _curve_status(curve):
    values = [x for x in curve if x.get("value") is not None]
    stale = [x for x in values if x.get("stale")]
    if not values:
        return "데이터 없음"
    if stale:
        return f"{len(stale)}개 만기 최근 성공값 사용"
    return "최신 ECOS/FRED 데이터"


async def render_bond_panel(host, us_curve=None, kr_curve=None):
    """Fast bond UI.

    Current curves render immediately. Historical matrices and spreads are loaded
    only when their tabs are opened, so the dashboard no longer waits for them.
    """
    host.clear()
    with host:
        with ui.tabs().classes("w-full dashboard-tabs") as tabs:
            current_tab = ui.tab("현재 YC", icon="timeline")
            history_tab = ui.tab("시점별 YC", icon="history")
            spread_tab = ui.tab("스프레드", icon="show_chart")

        with ui.tab_panels(tabs, value=current_tab).classes("w-full bg-transparent"):
            with ui.tab_panel(current_tab).classes("p-0 pt-3"):
                current_host = ui.column().classes("w-full")
            with ui.tab_panel(history_tab).classes("p-0 pt-3"):
                history_host = ui.column().classes("w-full gap-4")
                with history_host:
                    ui.label("탭을 열면 5년치 금리곡선 데이터를 한 번만 불러옵니다.").classes("text-xs muted")
            with ui.tab_panel(spread_tab).classes("p-0 pt-3"):
                spread_host = ui.column().classes("w-full gap-4")
                with spread_host:
                    ui.label("탭을 열면 장단기 금리차를 불러옵니다.").classes("text-xs muted")

    async def load_current():
        nonlocal us_curve, kr_curve
        if us_curve is None or kr_curve is None:
            from global_market_data import get_kr_yield_curve, get_us_yield_curve
            us_curve, kr_curve = await asyncio.gather(
                asyncio.to_thread(get_us_yield_curve),
                asyncio.to_thread(get_kr_yield_curve),
            )
        current_host.clear()
        with current_host:
            with ui.grid(columns=2).classes("w-full gap-4 max-md:grid-cols-1"):
                for country, title, curve in [
                    ("us", "미국 국채 수익률", us_curve),
                    ("kr", "한국 국고채 수익률", kr_curve),
                ]:
                    with ui.card().classes("surface p-5"):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label(title).classes("font-bold main-text")
                            ui.label(_curve_status(curve)).classes("text-[10px] muted")
                        ui.echart(_current_curve_options(curve, title), renderer="canvas").classes("w-full h-[300px]")
                        with ui.row().classes("w-full gap-2 flex-wrap mt-2"):
                            for point in curve:
                                tenor = point.get("tenor")
                                value = point.get("value")
                                text = tenor if value is None else f"{tenor} {value:.2f}%"
                                ui.button(
                                    text,
                                    on_click=lambda _, c=country, t=tenor: ui.navigate.to(f"/bond/{c}/{t}"),
                                ).props("outline dense no-caps").classes("text-xs")

    history_loaded = {"done": False}
    spread_loaded = {"done": False}

    async def load_history():
        if history_loaded["done"]:
            return
        history_loaded["done"] = True
        history_host.clear()
        with history_host:
            ui.spinner(size="md").classes("m-8 self-center")

        us_dates, kr_dates = await asyncio.gather(
            asyncio.to_thread(curve_available_dates, "us", 5),
            asyncio.to_thread(curve_available_dates, "kr", 5),
        )
        history_host.clear()

        with history_host:
            ui.label("슬라이더를 움직이면 그 시점의 Yield Curve를 현재 곡선과 비교합니다.").classes("text-xs muted")
            with ui.grid(columns=2).classes("w-full gap-4 max-md:grid-cols-1"):
                for country, title, dates, current_curve in [
                    ("us", "미국 Yield Curve 시점 비교", us_dates, us_curve or []),
                    ("kr", "한국 Yield Curve 시점 비교", kr_dates, kr_curve or []),
                ]:
                    with ui.card().classes("surface p-4"):
                        if not dates:
                            ui.label("역사 데이터를 불러오지 못했습니다.").classes("muted p-5")
                            continue
                        # Downsample slider to roughly weekly dates; source data stays fully cached.
                        sampled = dates[::5] if len(dates) > 250 else dates
                        if sampled[-1] != dates[-1]:
                            sampled.append(dates[-1])
                        selected = sampled[-1]
                        selected_curve = await asyncio.to_thread(curve_at_date, country, selected, 5)
                        chart = ui.echart(
                            _current_curve_options(current_curve, title, selected_curve, selected),
                            renderer="canvas",
                        ).classes("w-full h-[360px]")
                        date_label = ui.label(selected).classes("text-xs font-bold main-text")
                        slider = ui.slider(min=0, max=len(sampled) - 1, value=len(sampled) - 1, step=1).classes("w-full")

                        async def change_date(event, c=country, ds=sampled, ch=chart, label=date_label, cur=current_curve, ttl=title):
                            idx = max(0, min(len(ds) - 1, int(event.value)))
                            date = ds[idx]
                            compare = await asyncio.to_thread(curve_at_date, c, date, 5)
                            label.set_text(date)
                            options = _current_curve_options(cur, ttl, compare, date)
                            ch.options.clear()
                            ch.options.update(options)
                            ch.update()

                        slider.on("update:model-value", change_date, throttle=0.18, leading_events=False, trailing_events=True)

    async def load_spreads():
        if spread_loaded["done"]:
            return
        spread_loaded["done"] = True
        spread_host.clear()
        with spread_host:
            ui.spinner(size="md").classes("m-8 self-center")
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
                            ui.label("2년물 데이터가 없어 스프레드를 계산하지 못했습니다.").classes("text-xs muted p-4")

    async def tab_changed(event):
        value = str(event.value)
        if "시점별 YC" in value or value == str(history_tab):
            await load_history()
        elif "스프레드" in value or value == str(spread_tab):
            await load_spreads()

    tabs.on("update:model-value", tab_changed)
    await load_current()
