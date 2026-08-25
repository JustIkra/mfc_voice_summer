from __future__ import annotations

from collections.abc import Sequence

from call_analytics.service.ports import (
    CallRecordingSource,
    CallRecordingSourceError,
    CallRepository,
    InvalidRecordingError,
    RecordingWorkspace,
    TelephonyGateway,
    TelephonyGatewayError,
)
from domain import AudioBlob, CallRecording, Period, RecordingId


class RecoveringRecordingSource(CallRecordingSource):
    def __init__(
        self,
        primary: CallRecordingSource,
        workspace: RecordingWorkspace,
        calls: CallRepository,
        gateway: TelephonyGateway,
    ) -> None:
        self._primary = primary
        self._workspace = workspace
        self._calls = calls
        self._gateway = gateway

    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        return await self._primary.list_recordings(period)

    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        try:
            return await self._primary.fetch_audio(recording_id)
        except InvalidRecordingError:
            return await self._restore(recording_id)

    async def _restore(self, recording_id: RecordingId) -> AudioBlob:
        recording = await self._calls.load_recording(recording_id)
        source = recording.source_recording if recording is not None else None
        if source is None or source.acct_id is None:
            raise CallRecordingSourceError.not_found(
                f"telephony metadata is absent for {recording_id.value}"
            )
        try:
            filenames = source.filenames or await self._gateway.recording_files(source.acct_id)
            if not filenames:
                raise CallRecordingSourceError.not_found(
                    f"telephony recording is absent for {recording_id.value}"
                )
            parts = [await self._gateway.download_recording(filename) for filename in filenames]
            await self._workspace.prepare(recording_id, parts)
            return await self._workspace.load_audio(recording_id)
        except TelephonyGatewayError as error:
            raise _source_error(error) from error


def _source_error(error: TelephonyGatewayError) -> CallRecordingSourceError:
    if error.kind == "TIMEOUT":
        return CallRecordingSourceError.timeout(str(error))
    if error.kind == "NOT_FOUND":
        return CallRecordingSourceError.not_found(str(error))
    if error.kind == "AUTH":
        return CallRecordingSourceError.auth(str(error))
    if error.kind == "CONNECTION":
        return CallRecordingSourceError.connection(str(error))
    return CallRecordingSourceError.unexpected(str(error))


__all__ = ["RecoveringRecordingSource"]
