from __future__ import annotations

import json
import zlib
from typing import cast


def compress_payload(payload: dict[str, object]) -> bytes:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return zlib.compress(encoded, level=6)


def decompress_payload(data: bytes) -> dict[str, object]:
    decoded = zlib.decompress(data).decode("utf-8")
    return cast(dict[str, object], json.loads(decoded))


__all__ = ["compress_payload", "decompress_payload"]
