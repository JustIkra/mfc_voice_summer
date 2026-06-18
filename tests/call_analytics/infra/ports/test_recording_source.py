import pytest

from call_analytics.infra.ports.recording_source import (
    CallRecordingSource,
    CallRecordingSourceError,
)


def test_port_is_abstract() -> None:
    with pytest.raises(TypeError):
        CallRecordingSource()  # type: ignore[abstract]


def test_error_factory_sets_kind() -> None:
    err = CallRecordingSourceError.timeout("медленно")
    assert err.kind is CallRecordingSourceError.Kind.TIMEOUT
    assert "TIMEOUT" in str(err)
