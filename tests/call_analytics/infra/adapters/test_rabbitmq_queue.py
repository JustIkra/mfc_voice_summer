from __future__ import annotations

from call_analytics.infra.adapters.queue import (
    decode_processing_message,
    encode_processing_message,
)
from domain import RecordingId


def test_processing_queue_payload_round_trips_recording_id() -> None:
    body = encode_processing_message(RecordingId("call-42"))

    recording_id = decode_processing_message(body)

    assert body == b'{"recording_id": "call-42"}'
    assert recording_id == RecordingId("call-42")
