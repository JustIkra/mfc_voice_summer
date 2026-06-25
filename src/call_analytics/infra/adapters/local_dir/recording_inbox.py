from __future__ import annotations

import re
from pathlib import Path

from call_analytics.infra.adapters.local_dir.recording_source import (
    LocalDirectoryRecordingSource,
)
from call_analytics.service.ports import RecordingInbox
from domain import CallRecording

_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9А-Яа-я._-]+")


class LocalDirectoryRecordingInbox(RecordingInbox):
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def save_wav(self, filename: str, content: bytes) -> CallRecording:
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self._next_path(self._safe_name(filename))
        target.write_bytes(content)
        return LocalDirectoryRecordingSource(self._directory)._to_recording(target)

    def _safe_name(self, filename: str) -> str:
        source_name = Path(filename).name
        stem = Path(source_name).stem.strip()
        safe_stem = _SAFE_STEM_RE.sub("-", stem).strip(".-_")
        if not safe_stem:
            safe_stem = "recording"
        return f"{safe_stem}.wav"

    def _next_path(self, filename: str) -> Path:
        candidate = self._directory / filename
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        for index in range(1, 10_000):
            next_candidate = self._directory / f"{stem}-{index}.wav"
            if not next_candidate.exists():
                return next_candidate
        raise OSError(f"не удалось подобрать имя файла для {filename}")


__all__ = ["LocalDirectoryRecordingInbox"]
