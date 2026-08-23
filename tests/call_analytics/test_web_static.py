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
    assert "Эмоциональный окрас" in script
    assert "Ключевые моменты" not in script
    assert 'reportList("Риски"' not in script
    assert 'reportList("Рекомендации"' not in script
    assert "new WebSocket(" not in script


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
