from call_analytics.infra import ports


def test_ports_boundary_exports() -> None:
    expected = {
        "ArtifactStore",
        "CallRecordingSource",
        "CallRecordingSourceError",
        "EmotionRecognizer",
        "EmotionRecognizerError",
        "JobRepository",
        "ModelAudio",
        "ModelAudioStager",
        "Period",
        "ProcessingMessage",
        "ProcessingQueue",
        "ProcessingQueueError",
        "ReportGenerator",
        "ReportGeneratorError",
        "ReportRenderer",
        "ReportRendererError",
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


def test_legacy_port_modules_reexport_application_ports() -> None:
    from call_analytics.infra.ports.recording_source import (
        CallRecordingSource as LegacyRecordingSource,
    )
    from call_analytics.infra.ports.transcriber import Transcriber as LegacyTranscriber
    from call_analytics.service.ports import CallRecordingSource, Transcriber

    assert LegacyRecordingSource is CallRecordingSource
    assert LegacyTranscriber is Transcriber
