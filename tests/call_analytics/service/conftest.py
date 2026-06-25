from __future__ import annotations

from collections.abc import Sequence

from call_analytics.infra.ports import CallRecordingSource, Period, Transcriber
from domain import AudioBlob, CallRecording, ChannelLayout, RecordingId, Transcript


class FakeRecordingSource(CallRecordingSource):
    """Фейковый источник: отдаёт заранее положенное аудио."""

    def __init__(self, audio: dict[str, AudioBlob]) -> None:
        self._audio = audio

    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        return []

    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        return self._audio[recording_id.value]


class FailingTranscriber(Transcriber):
    """Транскрайбер, бросающий контрактную ошибку при первом вызове."""

    def __init__(self, error: Exception, then: Transcriber) -> None:
        self._error = error
        self._then = then
        self.calls = 0

    async def transcribe(self, recording_id: RecordingId, audio: AudioBlob) -> Transcript:
        self.calls += 1
        if self.calls == 1:
            raise self._error
        return await self._then.transcribe(recording_id, audio)


def stereo_blob() -> AudioBlob:
    return AudioBlob(data=b"x", codec="wav/gsm0610", layout=ChannelLayout.STEREO)
