from datetime import timedelta

from domain.diarization import SpeakerRole
from domain.emotion import EmotionAnalysis, EmotionLabel, SegmentEmotion
from domain.recording import RecordingId
from domain.transcript import TimeSpan


def test_emotion_analysis_holds_scores() -> None:
    se = SegmentEmotion(
        span=TimeSpan(start=timedelta(0), end=timedelta(seconds=2)),
        role=SpeakerRole.CLIENT,
        label=EmotionLabel.ANGRY,
        scores={EmotionLabel.ANGRY: 0.8, EmotionLabel.NEUTRAL: 0.2},
    )
    ea = EmotionAnalysis(recording_id=RecordingId("rec-1"), segments=(se,))
    assert ea.segments[0].label is EmotionLabel.ANGRY
    assert ea.segments[0].scores[EmotionLabel.ANGRY] == 0.8
