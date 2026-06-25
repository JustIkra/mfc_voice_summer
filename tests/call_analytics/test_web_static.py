from __future__ import annotations

from pathlib import Path


def test_upload_control_copy_and_accept_filter() -> None:
    html = Path("src/call_analytics/web_static/index.html").read_text(encoding="utf-8")
    script = Path("src/call_analytics/web_static/assets/app.js").read_text(encoding="utf-8")

    assert 'id="uploadButton">Загрузить<' in html
    assert 'accept=".wav,audio/wav,audio/x-wav,audio/wave,audio/*"' in html
    assert "Запись поставлена в очередь" in script
    assert "WAV поставлен" not in script


def test_recordings_list_has_search_control() -> None:
    html = Path("src/call_analytics/web_static/index.html").read_text(encoding="utf-8")
    script = Path("src/call_analytics/web_static/assets/app.js").read_text(encoding="utf-8")

    assert 'id="recordingSearch"' in html
    assert 'type="search"' in html
    assert "Поиск" in html
    assert "visibleRecordings" in script
    assert "searchQuery" in script
    assert "Ничего не найдено" in script


def test_app_js_subscribes_to_job_status_events_with_refresh_fallback() -> None:
    script = Path("src/call_analytics/web_static/assets/app.js").read_text(encoding="utf-8")

    assert "new WebSocket(" in script
    assert "/api/jobs/" in script
    assert "/events" in script
    assert "refresh();" in script


def test_app_js_does_not_offer_manual_processing_bypass() -> None:
    script = Path("src/call_analytics/web_static/assets/app.js").read_text(encoding="utf-8")
    html = Path("src/call_analytics/web_static/index.html").read_text(encoding="utf-8")

    assert "Обработать" not in script
    assert 'data-action="process"' not in script
    assert "/process" not in script
    assert "Обработать" not in html


def test_app_js_offers_delete_and_overwrite_report_actions() -> None:
    script = Path("src/call_analytics/web_static/assets/app.js").read_text(encoding="utf-8")

    assert "Удалить отчёт" in script
    assert "Перезаписать" in script
    assert 'data-action="delete-report"' in script
    assert 'data-action="overwrite"' in script
    assert "/report" in script
    assert "/overwrite" in script
    assert "confirm(" in script


def test_web_image_installs_cyrillic_pdf_font() -> None:
    dockerfile = Path("docker/web/Dockerfile").read_text(encoding="utf-8")

    assert "fonts-dejavu-core" in dockerfile
