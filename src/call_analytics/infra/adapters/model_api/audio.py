from __future__ import annotations

from pathlib import Path

from call_analytics.service.ports import ModelAudio, ModelAudioStager
from domain import AudioBlob, RecordingId


class MountedDirectoryAudioStager(ModelAudioStager):
    def __init__(self, host_directory: Path, model_directory: str) -> None:
        self._host_directory = host_directory
        self._model_directory = model_directory

    async def stage(self, recording_id: RecordingId, audio: AudioBlob) -> ModelAudio:
        filename = f"{recording_id.value}.wav"
        path = self._host_directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio.data)
        return ModelAudio(path=str(Path(self._model_directory) / filename))


__all__ = ["MountedDirectoryAudioStager"]
