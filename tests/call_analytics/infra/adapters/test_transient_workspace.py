from __future__ import annotations

import io
import os
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.transient import FilesystemRecordingWorkspace
from call_analytics.service.ports import InvalidRecordingError
from domain import ChannelLayout, RecordingId

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))


def _wav(frames: int = 1600) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x01\x00" * frames)
    return buffer.getvalue()


async def test_workspace_prepares_loads_and_clears_pcm_parts(tmp_path: Path) -> None:
    workspace = FilesystemRecordingWorkspace(tmp_path, "/data/staging")
    recording_id = RecordingId("cdr:group-001")

    prepared = await workspace.prepare(recording_id, [_wav(800), _wav(800)])
    audio = await workspace.load_audio(recording_id)

    assert prepared.duration == timedelta(seconds=0.1)
    assert prepared.layout is ChannelLayout.MONO
    assert audio.layout is ChannelLayout.MONO
    assert workspace.path_for(recording_id).is_dir()

    await workspace.clear(recording_id)

    assert not workspace.path_for(recording_id).exists()


async def test_workspace_rejects_empty_and_corrupt_parts(tmp_path: Path) -> None:
    workspace = FilesystemRecordingWorkspace(tmp_path, "/data/staging")

    with pytest.raises(InvalidRecordingError):
        await workspace.prepare(RecordingId("empty"), [b""])
    with pytest.raises(InvalidRecordingError):
        await workspace.prepare(RecordingId("corrupt"), [b"not-wave"])


async def test_workspace_clears_only_stale_hashed_job_directories(tmp_path: Path) -> None:
    workspace = FilesystemRecordingWorkspace(tmp_path, "/data/staging")
    old_id = RecordingId("old")
    fresh_id = RecordingId("fresh")
    await workspace.prepare(old_id, [_wav()])
    await workspace.prepare(fresh_id, [_wav()])
    old_timestamp = datetime(2026, 8, 20, tzinfo=MSK).timestamp()
    os.utime(workspace.path_for(old_id), (old_timestamp, old_timestamp))

    cleared = await workspace.clear_stale(datetime(2026, 8, 21, tzinfo=MSK))

    assert cleared == 1
    assert not workspace.path_for(old_id).exists()
    assert workspace.path_for(fresh_id).exists()


async def test_workspace_preserves_protected_stale_job_directories(tmp_path: Path) -> None:
    workspace = FilesystemRecordingWorkspace(tmp_path, "/data/staging")
    protected_id = RecordingId("protected")
    orphaned_id = RecordingId("orphaned")
    await workspace.prepare(protected_id, [_wav()])
    await workspace.prepare(orphaned_id, [_wav()])
    old_timestamp = datetime(2026, 8, 20, tzinfo=MSK).timestamp()
    os.utime(workspace.path_for(protected_id), (old_timestamp, old_timestamp))
    os.utime(workspace.path_for(orphaned_id), (old_timestamp, old_timestamp))

    cleared = await workspace.clear_stale(
        datetime(2026, 8, 21, tzinfo=MSK),
        protected=(protected_id,),
    )

    assert cleared == 1
    assert workspace.path_for(protected_id).exists()
    assert not workspace.path_for(orphaned_id).exists()
