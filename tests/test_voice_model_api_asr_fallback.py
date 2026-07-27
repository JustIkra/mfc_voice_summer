from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FALLBACK_MODULE = ROOT / "docker" / "voice-model-api" / "asr_fallback.py"


def load_fallback_module() -> Any:
    spec = importlib.util.spec_from_file_location("voice_model_asr_fallback", FALLBACK_MODULE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlignmentSensitiveModel:
    def transcribe(self, _path: str, *, word_timestamps: bool, **_options: Any) -> tuple[Any, str]:
        if word_timestamps:
            return self._failed_alignment(), "primary"
        return iter(("fallback segment",)), "fallback"

    def _failed_alignment(self) -> Any:
        raise RuntimeError("parallel_for failed: cudaErrorInvalidDevice: invalid device ordinal")
        yield


class BrokenDecoderModel:
    def transcribe(self, _path: str, *, word_timestamps: bool, **_options: Any) -> tuple[Any, str]:
        if word_timestamps:
            return self._failed_decode(), "primary"
        return iter(("unexpected fallback",)), "fallback"

    def _failed_decode(self) -> Any:
        raise RuntimeError("CUDA out of memory")
        yield


def test_transcription_retries_without_word_timestamps_after_alignment_device_error() -> None:
    module = load_fallback_module()

    segments, info, used_fallback = module.transcribe_with_word_timestamp_fallback(
        AlignmentSensitiveModel(),
        "/data/staging/problem.wav",
        language="ru",
    )

    assert segments == ["fallback segment"]
    assert info == "fallback"
    assert used_fallback is True


def test_transcription_does_not_mask_unrelated_runtime_error() -> None:
    module = load_fallback_module()

    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        module.transcribe_with_word_timestamp_fallback(
            BrokenDecoderModel(),
            "/data/staging/problem.wav",
            language="ru",
        )
