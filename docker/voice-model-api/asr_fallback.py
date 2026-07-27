from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class TranscriptionModel(Protocol):
    def transcribe(self, audio: str, **options: Any) -> tuple[Iterable[Any], Any]: ...


def transcribe_with_word_timestamp_fallback(
    model: TranscriptionModel,
    path: str,
    **options: Any,
) -> tuple[list[Any], Any, bool]:
    try:
        segments, info = model.transcribe(path, word_timestamps=True, **options)
        return list(segments), info, False
    except RuntimeError as error:
        if "cudaErrorInvalidDevice: invalid device ordinal" not in str(error):
            raise
        segments, info = model.transcribe(path, word_timestamps=False, **options)
        return list(segments), info, True


__all__ = ["transcribe_with_word_timestamp_fallback"]
