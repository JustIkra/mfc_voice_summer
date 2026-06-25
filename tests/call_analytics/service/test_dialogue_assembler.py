from __future__ import annotations

from datetime import timedelta

from call_analytics.service.dialogue import DialogueAssembler
from domain import (
    DiarizedSegment,
    DiarizedTranscript,
    EmotionAnalysis,
    EmotionLabel,
    RecordingId,
    SegmentEmotion,
    SpeakerRole,
    TimeSpan,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)

RID = RecordingId("call-1")


def span(start: float, end: float) -> TimeSpan:
    return TimeSpan(start=timedelta(seconds=start), end=timedelta(seconds=end))


def test_dialogue_uses_word_timestamps_and_attaches_emotion_episodes() -> None:
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(
            TranscriptSegment(
                span=span(0.0, 4.0),
                text="МФЦ здравствуйте хочу записаться",
                confidence=0.98,
                words=(
                    TranscriptWord(span=span(0.0, 0.5), text="МФЦ", confidence=0.99),
                    TranscriptWord(
                        span=span(0.5, 1.0),
                        text="здравствуйте",
                        confidence=0.98,
                    ),
                    TranscriptWord(span=span(2.0, 2.5), text="хочу", confidence=0.97),
                    TranscriptWord(
                        span=span(2.5, 3.2),
                        text="записаться",
                        confidence=0.96,
                    ),
                ),
            ),
        ),
        full_text="МФЦ здравствуйте хочу записаться",
    )
    diarized = DiarizedTranscript(
        recording_id=RID,
        segments=(
            DiarizedSegment(
                span=span(0.0, 1.2),
                role=SpeakerRole.UNKNOWN,
                text="",
                speaker="SPEAKER_00",
            ),
            DiarizedSegment(
                span=span(1.8, 3.4),
                role=SpeakerRole.UNKNOWN,
                text="",
                speaker="SPEAKER_01",
            ),
        ),
    )
    emotions = EmotionAnalysis(
        recording_id=RID,
        segments=(
            SegmentEmotion(
                span=span(0.0, 1.2),
                role=SpeakerRole.UNKNOWN,
                speaker="SPEAKER_00",
                label=EmotionLabel.NEUTRAL,
                score=0.8,
                scores={EmotionLabel.NEUTRAL: 0.8},
            ),
            SegmentEmotion(
                span=span(1.8, 3.4),
                role=SpeakerRole.UNKNOWN,
                speaker="SPEAKER_01",
                label=EmotionLabel.ANGRY,
                score=0.7,
                scores={EmotionLabel.ANGRY: 0.7},
            ),
        ),
    )

    dialogue = DialogueAssembler().assemble(transcript, diarized, emotions)

    assert [item.speaker for item in dialogue.utterances] == ["SPEAKER_00", "SPEAKER_01"]
    assert dialogue.utterances[0].text == "МФЦ здравствуйте"
    assert dialogue.utterances[1].text == "хочу записаться"
    assert dialogue.utterances[0].emotion_episodes[0].label == EmotionLabel.NEUTRAL
    assert dialogue.utterances[1].emotion_episodes[0].label == EmotionLabel.ANGRY


def test_dialogue_does_not_assign_zero_overlap_speaker() -> None:
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(
            TranscriptSegment(
                span=span(10.0, 11.0),
                text="Здравствуйте",
                words=(TranscriptWord(span=span(10.0, 11.0), text="Здравствуйте"),),
            ),
        ),
        full_text="Здравствуйте",
    )
    diarized = DiarizedTranscript(
        recording_id=RID,
        segments=(
            DiarizedSegment(
                span=span(0.0, 1.0),
                role=SpeakerRole.UNKNOWN,
                text="",
                speaker="SPEAKER_00",
            ),
        ),
    )
    emotions = EmotionAnalysis(recording_id=RID, segments=())

    dialogue = DialogueAssembler().assemble(transcript, diarized, emotions)

    assert dialogue.utterances[0].speaker is None
    assert dialogue.utterances[0].speaker_overlap_seconds == 0.0
    assert dialogue.utterances[0].speaker_coverage == 0.0
