import pytest

from call_analytics.infra.ports import (
    EmotionRecognizer,
    EmotionRecognizerError,
    ReportGenerator,
    ReportGeneratorError,
    SpeakerDiarizer,
    SpeakerDiarizerError,
    Transcriber,
    TranscriberError,
)


@pytest.mark.parametrize(
    "port",
    [Transcriber, SpeakerDiarizer, EmotionRecognizer, ReportGenerator],
)
def test_ports_are_abstract(port: type) -> None:
    with pytest.raises(TypeError):
        port()  # type: ignore[abstract]


def test_transcriber_error_kind() -> None:
    err = TranscriberError.invalid_format("не wav")
    assert err.kind is TranscriberError.Kind.INVALID_FORMAT


def test_diarizer_error_kind() -> None:
    err = SpeakerDiarizerError.unexpected("ой")
    assert err.kind is SpeakerDiarizerError.Kind.UNEXPECTED


def test_emotion_error_kind() -> None:
    err = EmotionRecognizerError.timeout("долго")
    assert err.kind is EmotionRecognizerError.Kind.TIMEOUT


def test_report_error_kind() -> None:
    err = ReportGeneratorError.rate_limit("429")
    assert err.kind is ReportGeneratorError.Kind.RATE_LIMIT
