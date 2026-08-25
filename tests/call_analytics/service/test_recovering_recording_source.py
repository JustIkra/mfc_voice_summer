from __future__ import annotations

import io
import wave
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.in_memory import InMemoryCallRepository
from call_analytics.infra.adapters.transient import FilesystemRecordingWorkspace
from call_analytics.service.ports import TelephonyAccount, TelephonyGateway
from call_analytics.service.recovering_recording_source import RecoveringRecordingSource
from domain import (
    CallProcessingJob,
    CallRecording,
    ChannelLayout,
    DiscoveredCall,
    Period,
    RecordingId,
    SourceRecordingIdentity,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 25, 13, 30, tzinfo=MSK)
RID = RecordingId("cdr:missing-workspace")


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x01\x00" * 1600)
    return buffer.getvalue()


class RecordingGateway(TelephonyGateway):
    def __init__(self) -> None:
        self.downloaded: list[str] = []

    async def list_accounts(self) -> Sequence[TelephonyAccount]:
        raise AssertionError("list_accounts is not used")

    async def list_calls(
        self,
        period: Period,
        accounts: Sequence[TelephonyAccount],
    ) -> Sequence[DiscoveredCall]:
        raise AssertionError("list_calls is not used")

    async def recording_files(self, acct_id: str) -> tuple[str, ...]:
        assert acct_id == "1139092"
        return ("queue-recording.wav",)

    async def download_recording(self, filename: str) -> bytes:
        self.downloaded.append(filename)
        return _wav()

    async def close(self) -> None:
        return None


async def test_source_restores_missing_workspace_audio_from_telephony(tmp_path: Path) -> None:
    workspace = FilesystemRecordingWorkspace(tmp_path, "/data/staging")
    calls = InMemoryCallRepository()
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(seconds=1),
        channel_layout=ChannelLayout.MONO,
        source_recording=SourceRecordingIdentity(acct_id="1139092"),
    )
    await calls.register(recording, CallProcessingJob.create(RID.value, RID, NOW))
    gateway = RecordingGateway()
    source = RecoveringRecordingSource(workspace, workspace, calls, gateway)

    audio = await source.fetch_audio(RID)

    assert audio.data == _wav()
    assert gateway.downloaded == ["queue-recording.wav"]
    assert workspace.path_for(RID).is_dir()
