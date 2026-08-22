from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import shutil
import subprocess
import wave
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path

from call_analytics.service.ports import (
    ArtifactStore,
    CallRecordingSource,
    InvalidRecordingError,
    PreparedAudio,
    RecordingWorkspace,
)
from domain import (
    AudioBlob,
    CallRecording,
    CallReport,
    ChannelLayout,
    DiarizedTranscript,
    EmotionAnalysis,
    Period,
    RecordingId,
    Transcript,
)

_HASHED_JOB = re.compile(r"[0-9a-f]{64}")
CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]]


class FilesystemRecordingWorkspace(RecordingWorkspace, ArtifactStore, CallRecordingSource):
    def __init__(
        self,
        host_directory: Path,
        model_directory: str,
        runner: CommandRunner | None = None,
    ) -> None:
        self._host_directory = host_directory
        self._model_directory = Path(model_directory)
        self._runner = runner or _run_command
        self._recordings: dict[str, CallRecording] = {}
        self._transcripts: dict[str, Transcript] = {}
        self._diarizations: dict[str, DiarizedTranscript] = {}
        self._emotions: dict[str, EmotionAnalysis] = {}
        self._reports: dict[str, CallReport] = {}
        self._report_pdfs: dict[str, bytes] = {}

    async def prepare(self, call_id: RecordingId, parts: Sequence[bytes]) -> PreparedAudio:
        return await asyncio.to_thread(self._prepare, call_id, parts)

    async def load_audio(self, call_id: RecordingId) -> AudioBlob:
        return await asyncio.to_thread(self._load_audio, call_id)

    async def clear(self, call_id: RecordingId) -> None:
        await asyncio.to_thread(self._clear_files, call_id)
        self._clear_objects(call_id)

    async def clear_stale(self, older_than: datetime) -> int:
        return await asyncio.to_thread(self._clear_stale, older_than)

    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        return [
            recording
            for recording in self._recordings.values()
            if period.start <= recording.started_at <= period.end
        ]

    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        return await self.load_audio(recording_id)

    async def save_recording(self, recording: CallRecording) -> None:
        self._recordings[recording.id.value] = recording

    async def load_recording(self, recording_id: RecordingId) -> CallRecording | None:
        return self._recordings.get(recording_id.value)

    async def save_transcript(self, transcript: Transcript) -> None:
        self._transcripts[transcript.recording_id.value] = transcript

    async def load_transcript(self, recording_id: RecordingId) -> Transcript | None:
        return self._transcripts.get(recording_id.value)

    async def save_diarization(self, diarized: DiarizedTranscript) -> None:
        self._diarizations[diarized.recording_id.value] = diarized

    async def load_diarization(self, recording_id: RecordingId) -> DiarizedTranscript | None:
        return self._diarizations.get(recording_id.value)

    async def save_emotion(self, emotion: EmotionAnalysis) -> None:
        self._emotions[emotion.recording_id.value] = emotion

    async def load_emotion(self, recording_id: RecordingId) -> EmotionAnalysis | None:
        return self._emotions.get(recording_id.value)

    async def save_report(self, report: CallReport) -> None:
        self._reports[report.recording_id.value] = report

    async def load_report(self, recording_id: RecordingId) -> CallReport | None:
        return self._reports.get(recording_id.value)

    async def save_report_pdf(self, recording_id: RecordingId, content: bytes) -> None:
        self._report_pdfs[recording_id.value] = content

    async def load_report_pdf(self, recording_id: RecordingId) -> bytes | None:
        return self._report_pdfs.get(recording_id.value)

    async def delete_outputs(self, recording_id: RecordingId) -> None:
        await self.clear(recording_id)

    def path_for(self, call_id: RecordingId) -> Path:
        return self._host_directory / "jobs" / _workspace_key(call_id)

    def model_path_for(self, call_id: RecordingId) -> Path:
        return self._model_directory / "jobs" / _workspace_key(call_id) / "model.wav"

    def _prepare(self, call_id: RecordingId, parts: Sequence[bytes]) -> PreparedAudio:
        if not parts or any(not part for part in parts):
            raise InvalidRecordingError("recording contains an empty part")
        job_directory = self.path_for(call_id)
        job_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            frames = [
                self._normalized_frames(job_directory, index, part)
                for index, part in enumerate(parts)
            ]
            temporary = job_directory / "source.tmp.wav"
            source = job_directory / "source.wav"
            frame_count = sum(len(item) // 2 for item in frames)
            if frame_count <= 0:
                raise InvalidRecordingError("recording has zero duration")
            with wave.open(str(temporary), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                for item in frames:
                    output.writeframes(item)
            os.replace(temporary, source)
            source.chmod(0o600)
            return PreparedAudio(
                duration=timedelta(seconds=frame_count / 16000),
                layout=ChannelLayout.MONO,
                codec="wav",
            )
        except Exception:
            shutil.rmtree(job_directory, ignore_errors=True)
            raise

    def _normalized_frames(self, directory: Path, index: int, content: bytes) -> bytes:
        direct = _read_normalized_pcm(content)
        if direct is not None:
            return direct
        source = directory / f"part-{index:03d}.input"
        normalized = directory / f"part-{index:03d}.wav"
        source.write_bytes(content)
        result = self._runner(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(normalized),
            ]
        )
        if result.returncode != 0 or not normalized.is_file():
            raise InvalidRecordingError("ffmpeg rejected recording part")
        frames = _read_normalized_pcm(normalized.read_bytes())
        if frames is None:
            raise InvalidRecordingError("normalized recording is invalid")
        return frames

    def _load_audio(self, call_id: RecordingId) -> AudioBlob:
        source = self.path_for(call_id) / "source.wav"
        if not source.is_file():
            raise InvalidRecordingError(f"prepared recording {call_id.value} is absent")
        return AudioBlob(data=source.read_bytes(), codec="wav", layout=ChannelLayout.MONO)

    def _clear_files(self, call_id: RecordingId) -> None:
        shutil.rmtree(self.path_for(call_id), ignore_errors=True)

    def _clear_objects(self, call_id: RecordingId) -> None:
        key = call_id.value
        self._recordings.pop(key, None)
        self._transcripts.pop(key, None)
        self._diarizations.pop(key, None)
        self._emotions.pop(key, None)
        self._reports.pop(key, None)
        self._report_pdfs.pop(key, None)

    def _clear_stale(self, older_than: datetime) -> int:
        jobs_directory = self._host_directory / "jobs"
        if not jobs_directory.is_dir():
            return 0
        cutoff = older_than.timestamp()
        cleared = 0
        for candidate in jobs_directory.iterdir():
            if not candidate.is_dir() or _HASHED_JOB.fullmatch(candidate.name) is None:
                continue
            if candidate.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(candidate)
            cleared += 1
        return cleared


def _workspace_key(call_id: RecordingId) -> str:
    return hashlib.sha256(call_id.value.encode()).hexdigest()


def _read_normalized_pcm(content: bytes) -> bytes | None:
    try:
        with wave.open(io.BytesIO(content), "rb") as source:
            if (
                source.getnchannels() != 1
                or source.getsampwidth() != 2
                or source.getframerate() != 16000
                or source.getcomptype() != "NONE"
            ):
                return None
            return source.readframes(source.getnframes())
    except (EOFError, wave.Error):
        return None


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False)


__all__ = ["FilesystemRecordingWorkspace"]
