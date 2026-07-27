from __future__ import annotations

from collections.abc import Sequence

from call_analytics.service.ports import (
    CallRecordingSource,
    CallRecordingSourceError,
    Period,
)
from domain import AudioBlob, CallRecording, RecordingId


class CompositeRecordingSource(CallRecordingSource):
    def __init__(self, *sources: CallRecordingSource) -> None:
        self._sources = sources

    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        recordings: list[CallRecording] = []
        for source in self._sources:
            recordings.extend(await source.list_recordings(period))
        return recordings

    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        for source in self._sources:
            try:
                return await source.fetch_audio(recording_id)
            except CallRecordingSourceError as error:
                if error.kind is not CallRecordingSourceError.Kind.NOT_FOUND:
                    raise
        raise CallRecordingSourceError.not_found(
            f"файл записи {recording_id.value} не найден ни в одном источнике"
        )


__all__ = ["CompositeRecordingSource"]
