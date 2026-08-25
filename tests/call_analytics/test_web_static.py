from __future__ import annotations

from pathlib import Path


def _read(relative: str) -> str:
    return (Path("src/call_analytics/web_static") / relative).read_text(encoding="utf-8")


def test_dashboard_has_approved_structure_without_recording_controls() -> None:
    html = _read("index.html")
    script = _read("assets/app.js")

    for element_id in (
        "dateFrom",
        "dateTo",
        "operatorSelect",
        "satisfactionSelect",
        "resolutionSelect",
        "sortSelect",
        "callSearch",
        "qualityRibbon",
        "resolutionYes",
        "resolutionPartial",
        "resolutionNo",
        "resolutionUnknown",
        "summaryMetrics",
        "operatorBoard",
        "callJournal",
        "reportDialog",
        "syncStatus",
    ):
        assert f'id="{element_id}"' in html
    assert 'class="quality-legend"' in html
    assert html.index('id="operatorBoard"') < html.index('id="filterForm"')
    assert html.index('id="filterForm"') < html.index('id="callJournal"')
    assert "Применить фильтры" in html
    assert "Эмоция клиента" in html
    assert "Вопрос решён" in html
    assert 'colspan="9"' in html
    assert "<audio" not in html.lower()
    assert "upload" not in html.lower()
    assert "прослуш" not in html.lower()
    assert "/api/dashboard/summary" in script
    assert "/api/operators" in script
    assert "/api/calls" in script
    assert "/api/sync/status" in script


def test_frontend_uses_server_filters_pagination_and_cancellable_requests() -> None:
    script = _read("assets/app.js")

    assert "pageSize: 50" in script
    assert "URLSearchParams" in script
    assert "AbortController" in script
    assert "Promise.all" in script
    assert "showModal()" in script
    assert "report.pdf" in script
    assert "processing.pending" in script
    assert "Очередь:" in script
    assert "setInterval(pollSyncStatus, 10000)" in script
    assert 'params.set("operator_extension"' in script
    assert 'params.set("sort"' in script
    assert "Эмоциональный окрас" in script
    assert "Ключевые моменты" not in script
    assert 'reportList("Риски"' not in script
    assert 'reportList("Рекомендации"' not in script
    assert "new WebSocket(" not in script


def test_filter_dropdowns_share_aligned_full_width_custom_control() -> None:
    html = _read("index.html")
    script = _read("assets/app.js")
    css = _read("assets/app.css")

    for name in ("operator", "satisfaction", "resolution", "sort"):
        assert f'id="{name}Select" type="hidden"' in html
        assert f'id="{name}Trigger"' in html
        assert f'id="{name}Menu" role="listbox"' in html
        assert f'<select id="{name}Select"' not in html
    assert html.count("data-custom-select") == 4
    assert "setupCustomSelect" in script
    assert "openCustomSelect" in script
    assert "closeCustomSelect" in script
    assert "setCustomSelectValue" in script
    assert "setCustomSelectOptions(nodes.operator" in script
    assert "openSortMenu" not in script
    assert ".custom-select-trigger" in css
    assert ".custom-select-menu" in css
    assert "top: calc(100% + 0.35rem)" in css
    assert "right: auto" in css
    assert "width: max-content" in css
    assert "min-width: 100%" in css
    assert "max-width: min(32rem, calc(100vw - 2rem))" in css
    assert "padding: 0 0.8rem 0 2rem" in css
    assert "top: 50%" in css


def test_operator_card_shows_only_individual_resolved_percent() -> None:
    html = _read("index.html")
    script = _read("assets/app.js")

    assert "Доля обращений, где вопрос решён полностью" in html
    assert "позитивной эмоцией" not in html
    assert "operator.satisfied_percent" not in script
    assert "operator.resolved_percent" in script
    assert "<small>решено</small>" not in script
    assert "нагрузка" not in html.lower()


def test_partial_resolution_card_uses_white_text_on_amber() -> None:
    css = _read("assets/app.css")

    assert ".resolution-grid .partial {\n  color: white;\n  background: var(--amber);\n}" in css


def test_audio_player_exists_only_in_report_renderer() -> None:
    html = _read("index.html")
    script = _read("assets/app.js")
    css = _read("assets/app.css")
    journal_renderer = script[
        script.index("function renderCalls") : script.index("function renderPagination")
    ]

    assert "renderAudioPlayer" in script
    assert '<audio controls preload="metadata"' in script
    assert "Запись разговора" in script
    assert "Запись готовится" in script
    assert "<audio" not in html.lower()
    assert "<audio" not in journal_renderer
    assert '.querySelector("audio")?.pause()' in script
    assert ".recording-player" in css
    assert ".recording-player audio" in css


def test_sync_tooltip_describes_recording_storage() -> None:
    script = _read("assets/app.js")

    assert "Архив записей" in script
    assert "storage.free_bytes" in script
    assert "Критически мало места" in script


def test_styles_use_approved_tokens_fonts_and_breakpoints() -> None:
    css = _read("assets/app.css").lower()

    for color in ("#e8eef1", "#f9fbfb", "#10212b", "#143c4a", "#0b7d83"):
        assert color in css
    assert "@font-face" in css
    assert "onest-variable.ttf" in css
    assert "ibmplexmono-regular.ttf" in css
    assert "fonts.googleapis" not in css
    assert "@media (max-width: 1200px)" in css
    assert "@media (max-width: 1024px)" in css
    assert "@media (max-width: 767px)" in css
    assert "prefers-reduced-motion" in css
    assert "linear-gradient(rgba(20, 60, 74" not in css
    assert ".dashboard-grid" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in css
    assert "grid-column: span 2" in css
    assert "align-items: stretch" in css


def test_font_assets_and_licenses_are_bundled() -> None:
    fonts = Path("src/call_analytics/web_static/assets/fonts")

    for name in (
        "Onest-Variable.ttf",
        "IBMPlexMono-Regular.ttf",
        "OFL-Onest.txt",
        "OFL-IBMPlex.txt",
    ):
        assert (fonts / name).is_file()
