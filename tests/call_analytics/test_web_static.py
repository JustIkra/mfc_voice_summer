from __future__ import annotations

from pathlib import Path


def test_upload_control_copy_and_accept_filter() -> None:
    html = Path("src/call_analytics/web_static/index.html").read_text(encoding="utf-8")

    assert 'id="uploadButton">Загрузить<' in html
    assert 'accept=".wav,audio/wav,audio/x-wav,audio/wave,audio/*"' in html
