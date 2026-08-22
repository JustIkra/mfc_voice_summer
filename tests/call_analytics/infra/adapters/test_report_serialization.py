from __future__ import annotations

from call_analytics.infra.adapters.sqlite.serialization import (
    compress_payload,
    decompress_payload,
)


def test_report_payload_zlib_round_trip_is_deterministic() -> None:
    first = {"summary": "Вопрос решён", "schema_version": 1}
    second = {"schema_version": 1, "summary": "Вопрос решён"}

    first_compressed = compress_payload(first)
    second_compressed = compress_payload(second)

    assert first_compressed == second_compressed
    assert decompress_payload(first_compressed) == first
