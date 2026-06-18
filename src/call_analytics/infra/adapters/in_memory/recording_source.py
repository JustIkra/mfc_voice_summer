from __future__ import annotations

from collections.abc import Sequence

from call_analytics.infra.ports import (
    CallRecordingSource,
    CallRecordingSourceError,
    Period,
)
from domain import AudioBlob, CallRecording, RecordingId


class InMemoryRecordingSource(CallRecordingSource):
    """Словарный источник записей для демо/тестов.

    Хранит метаданные записей и их аудио в памяти. `fetch_audio` на
    отсутствующий идентификатор бросает контрактную ошибку
    `CallRecordingSourceError` с `Kind.NOT_FOUND`.
    """

    def __init__(self) -> None:
        self._recordings: dict[str, CallRecording] = {}
        self._audio: dict[str, AudioBlob] = {}

    def add(self, recording: CallRecording, audio: AudioBlob) -> None:
        """Положить запись и её аудио в источник."""
        self._recordings[recording.id.value] = recording
        self._audio[recording.id.value] = audio

    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        return [
            recording
            for recording in self._recordings.values()
            if period.start <= recording.started_at <= period.end
        ]

    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        audio = self._audio.get(recording_id.value)
        if audio is None:
            raise CallRecordingSourceError.not_found(recording_id.value)
        return audio


__all__ = ["InMemoryRecordingSource"]
