from call_analytics.infra import ports


def test_ports_boundary_exports() -> None:
    expected = {
        "ArtifactStore",
        "CallRecordingSource",
        "CallRecordingSourceError",
        "EmotionRecognizer",
        "EmotionRecognizerError",
        "JobRepository",
        "Period",
        "ReportGenerator",
        "ReportGeneratorError",
        "SpeakerDiarizer",
        "SpeakerDiarizerError",
        "Transcriber",
        "TranscriberError",
    }
    assert expected == set(ports.__all__)


def test_imports_from_boundary() -> None:
    from call_analytics.infra.ports import CallRecordingSource, Transcriber

    assert CallRecordingSource is not None
    assert Transcriber is not None
