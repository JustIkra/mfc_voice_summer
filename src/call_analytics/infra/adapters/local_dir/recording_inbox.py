from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

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
        safe_name = self._safe_name(filename)
        temporary = self._temporary_path(safe_name)
        source = LocalDirectoryRecordingSource(self._directory)
        try:
            temporary.write_bytes(content)
            source._to_recording(temporary)
            target = self._link_to_next_available_path(temporary, safe_name)
            return source._to_recording(target)
        finally:
            temporary.unlink(missing_ok=True)

    def _safe_name(self, filename: str) -> str:
        source_name = Path(filename).name
        stem = Path(source_name).stem.strip()
        safe_stem = _SAFE_STEM_RE.sub("-", stem).strip(".-_")
        if not safe_stem:
            safe_stem = "recording"
        return f"{safe_stem}.wav"

    def _link_to_next_available_path(self, temporary: Path, filename: str) -> Path:
        for candidate in self._candidate_paths(filename):
            try:
                os.link(temporary, candidate)
            except FileExistsError:
                continue
            return candidate
        raise OSError(f"не удалось подобрать имя файла для {filename}")

    def _candidate_paths(self, filename: str) -> Iterator[Path]:
        candidate = self._directory / filename
        yield candidate
        stem = candidate.stem
        for index in range(1, 10_000):
            yield self._directory / f"{stem}-{index}.wav"

    def _temporary_path(self, filename: str) -> Path:
        return self._directory / f".{filename}.{os.getpid()}.{uuid4().hex}.upload"


__all__ = ["LocalDirectoryRecordingInbox"]
