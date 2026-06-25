from __future__ import annotations

import re
import wave
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from call_analytics.service.ports import (
    CallRecordingSource,
    CallRecordingSourceError,
    Period,
)
from domain import AudioBlob, CallRecording, ChannelLayout, RecordingId

MSK = timezone(timedelta(hours=3))
_EPOCH_RE = re.compile(r"(\d{10}\.\d+)")
_DATETIME_RE = re.compile(r"(\d{8})-(\d{6})")


class LocalDirectoryRecordingSource(CallRecordingSource):
    """Источник записей из локального каталога WAV-файлов.

    Каждый `*.wav` в каталоге — одна запись. Идентификатор записи —
    имя файла без расширения. Время начала разбирается из имени файла
    (unix-метка вида `1772427789.149782`, иначе `ГГГГММДД-ЧЧММСС`), а при
    неудаче берётся время изменения файла. Длительность и раскладку
    каналов (моно/стерео) определяет заголовок WAV.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        recordings: list[CallRecording] = []
        for path in sorted(self._wav_files()):
            try:
                recording = self._to_recording(path)
            except CallRecordingSourceError:
                continue
            if period.start <= recording.started_at <= period.end:
                recordings.append(recording)
        return recordings

    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        try:
            path = self._path_for_recording_id(recording_id)
        except ValueError as error:
            raise CallRecordingSourceError.not_found(
                f"идентификатор записи {recording_id.value} некорректен"
            ) from error
        if not path.is_file():
            raise CallRecordingSourceError.not_found(f"файл записи {path} не найден")
        layout = self._layout(path)
        try:
            data = path.read_bytes()
        except OSError as error:
            raise CallRecordingSourceError.unexpected(str(error)) from error
        return AudioBlob(data=data, codec="wav", layout=layout)

    def _wav_files(self) -> list[Path]:
        try:
            return [p for p in self._directory.rglob("*") if p.suffix.lower() == ".wav"]
        except OSError as error:
            raise CallRecordingSourceError.unexpected(str(error)) from error

    def _to_recording(self, path: Path) -> CallRecording:
        nchannels, duration = self._wav_meta(path)
        return CallRecording(
            id=self._recording_id(path),
            started_at=self._started_at(path),
            duration=duration,
            channel_layout=ChannelLayout.STEREO
            if nchannels == 2
            else ChannelLayout.MONO,
            metadata={"filename": self._display_name(path)},
        )

    def _layout(self, path: Path) -> ChannelLayout:
        nchannels, _ = self._wav_meta(path)
        return ChannelLayout.STEREO if nchannels == 2 else ChannelLayout.MONO

    def _wav_meta(self, path: Path) -> tuple[int, timedelta]:
        try:
            with wave.open(str(path), "rb") as wav:
                nchannels = wav.getnchannels()
                frames = wav.getnframes()
                rate = wav.getframerate()
        except (wave.Error, OSError, EOFError) as error:
            raise CallRecordingSourceError.unexpected(
                f"не удалось прочитать WAV {path.name}: {error}"
            ) from error
        seconds = frames / rate if rate else 0.0
        return nchannels, timedelta(seconds=seconds)

    def _started_at(self, path: Path) -> datetime:
        epoch = _EPOCH_RE.search(path.stem)
        if epoch is not None:
            return datetime.fromtimestamp(float(epoch.group(1)), MSK)
        stamp = _DATETIME_RE.search(path.stem)
        if stamp is not None:
            return datetime.strptime(
                f"{stamp.group(1)}{stamp.group(2)}", "%Y%m%d%H%M%S"
            ).replace(tzinfo=MSK)
        return datetime.fromtimestamp(path.stat().st_mtime, MSK)

    def _recording_id(self, path: Path) -> RecordingId:
        if path.parent == self._directory:
            return RecordingId(path.stem)
        relative = path.relative_to(self._directory).with_suffix("").as_posix()
        return RecordingId(f"rel-{relative.encode('utf-8').hex()}")

    def _path_for_recording_id(self, recording_id: RecordingId) -> Path:
        value = recording_id.value
        if value.startswith("rel-"):
            relative = bytes.fromhex(value.removeprefix("rel-")).decode("utf-8")
            return self._directory / f"{relative}.wav"
        return self._directory / f"{value}.wav"

    def _display_name(self, path: Path) -> str:
        return path.relative_to(self._directory).as_posix()


__all__ = ["LocalDirectoryRecordingSource"]
