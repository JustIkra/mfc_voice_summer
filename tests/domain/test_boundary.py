import domain


def test_domain_public_surface() -> None:
    expected = {
        "STAGE_ORDER",
        "AudioBlob",
        "CallerIdentity",
        "CallerNameSource",
        "CallProcessingJob",
        "CallRecording",
        "CallReport",
        "ChannelLayout",
        "ClientSatisfaction",
        "DialogueQuality",
        "DialogueUtterance",
        "DiarizedSegment",
        "DiarizedTranscript",
        "DiscoveredCall",
        "EmotionalAssessment",
        "EmotionAnalysis",
        "EmotionEpisode",
        "EmotionLabel",
        "FinalReportDocument",
        "InvalidJobTransition",
        "JobStage",
        "JobStatus",
        "OperatorIdentity",
        "Period",
        "QueueIdentity",
        "QuestionResolution",
        "RecordingId",
        "Satisfaction",
        "SegmentEmotion",
        "SpeakerRole",
        "SourceRecordingIdentity",
        "SynchronizedDialogue",
        "TimeSpan",
        "Transcript",
        "TranscriptSegment",
        "TranscriptWord",
        "build_report_payload",
    }
    assert expected == set(domain.__all__)


def test_models_importable_from_boundary() -> None:
    from domain import CallProcessingJob, CallRecording, RecordingId

    assert CallRecording is not None
    assert CallProcessingJob is not None
    assert RecordingId is not None
