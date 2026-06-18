import domain


def test_domain_public_surface() -> None:
    expected = {
        "STAGE_ORDER",
        "AudioBlob",
        "CallProcessingJob",
        "CallRecording",
        "CallReport",
        "ChannelLayout",
        "DiarizedSegment",
        "DiarizedTranscript",
        "EmotionAnalysis",
        "EmotionLabel",
        "InvalidJobTransition",
        "JobStage",
        "JobStatus",
        "RecordingId",
        "Satisfaction",
        "SegmentEmotion",
        "SpeakerRole",
        "TimeSpan",
        "Transcript",
        "TranscriptSegment",
    }
    assert expected == set(domain.__all__)


def test_models_importable_from_boundary() -> None:
    from domain import CallProcessingJob, CallRecording, RecordingId

    assert CallRecording is not None
    assert CallProcessingJob is not None
    assert RecordingId is not None
