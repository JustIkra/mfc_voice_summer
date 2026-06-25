from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from domain import (
    DialogueQuality,
    DialogueUtterance,
    DiarizedSegment,
    DiarizedTranscript,
    EmotionAnalysis,
    EmotionEpisode,
    SynchronizedDialogue,
    TimeSpan,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)


def _seconds(value: timedelta) -> float:
    return value.total_seconds()


def _overlap(a: TimeSpan, b: TimeSpan) -> float:
    return max(
        0.0,
        min(_seconds(a.end), _seconds(b.end))
        - max(_seconds(a.start), _seconds(b.start)),
    )


@dataclass(frozen=True, slots=True)
class _SpeakerMatch:
    speaker: str | None
    seconds: float
    coverage: float


@dataclass(slots=True)
class _UtteranceDraft:
    span: TimeSpan
    speaker: str | None
    words: list[str]
    confidences: list[float]
    overlap: float
    coverages: list[float]


class DialogueAssembler:
    def __init__(
        self,
        min_overlap_seconds: float = 0.05,
        max_gap_seconds: float = 1.0,
    ) -> None:
        self._min_overlap_seconds = min_overlap_seconds
        self._max_gap_seconds = max_gap_seconds

    def assemble(
        self,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> SynchronizedDialogue:
        utterances = self._from_words(transcript, diarized)
        with_emotions = tuple(
            self._attach_emotions(utterance, emotions) for utterance in utterances
        )
        return SynchronizedDialogue(
            recording_id=transcript.recording_id,
            utterances=with_emotions,
            quality=self._quality(with_emotions),
        )

    def _from_words(
        self, transcript: Transcript, diarized: DiarizedTranscript
    ) -> tuple[DialogueUtterance, ...]:
        words = tuple(
            word
            for segment in transcript.segments
            for word in (segment.words or (self._segment_as_word(segment),))
            if word.text.strip()
        )
        grouped: list[_UtteranceDraft] = []
        current: _UtteranceDraft | None = None
        for word in words:
            match = self._best_speaker(word.span, diarized.segments)
            gap = (
                _seconds(word.span.start) - _seconds(current.span.end)
                if current
                else 0.0
            )
            should_start = (
                current is None
                or current.speaker != match.speaker
                or gap > self._max_gap_seconds
            )
            if should_start:
                current = _UtteranceDraft(
                    span=word.span,
                    speaker=match.speaker,
                    words=[word.text.strip()],
                    confidences=[word.confidence],
                    overlap=match.seconds,
                    coverages=[match.coverage],
                )
                grouped.append(current)
                continue

            assert current is not None
            current.span = TimeSpan(
                start=current.span.start,
                end=word.span.end,
            )
            current.words.append(word.text.strip())
            current.confidences.append(word.confidence)
            current.overlap += match.seconds
            current.coverages.append(match.coverage)

        return tuple(self._to_utterance(item) for item in grouped)

    def _segment_as_word(self, segment: TranscriptSegment) -> TranscriptWord:
        return TranscriptWord(
            span=segment.span,
            text=segment.text,
            confidence=segment.confidence,
        )

    def _best_speaker(
        self,
        span: TimeSpan,
        segments: tuple[DiarizedSegment, ...],
    ) -> _SpeakerMatch:
        duration = max(0.0, _seconds(span.end) - _seconds(span.start))
        totals: dict[str, float] = {}
        for segment in segments:
            if segment.speaker is None:
                continue
            seconds = _overlap(span, segment.span)
            if seconds <= 0:
                continue
            totals[segment.speaker] = totals.get(segment.speaker, 0.0) + seconds
        if not totals:
            return _SpeakerMatch(speaker=None, seconds=0.0, coverage=0.0)
        speaker, seconds = max(totals.items(), key=lambda item: item[1])
        coverage = seconds / duration if duration else 0.0
        if seconds < self._min_overlap_seconds:
            return _SpeakerMatch(speaker=None, seconds=seconds, coverage=coverage)
        return _SpeakerMatch(speaker=speaker, seconds=seconds, coverage=coverage)

    def _to_utterance(self, item: _UtteranceDraft) -> DialogueUtterance:
        return DialogueUtterance(
            span=item.span,
            speaker=item.speaker,
            text=" ".join(item.words),
            speaker_overlap_seconds=round(item.overlap, 3),
            speaker_coverage=round(sum(item.coverages) / len(item.coverages), 3)
            if item.coverages
            else 0.0,
            word_count=len(item.confidences),
            mean_word_confidence=round(
                sum(item.confidences) / len(item.confidences),
                3,
            )
            if item.confidences
            else None,
        )

    def _attach_emotions(
        self, utterance: DialogueUtterance, emotions: EmotionAnalysis
    ) -> DialogueUtterance:
        episodes = []
        for emotion in emotions.segments:
            if utterance.speaker and emotion.speaker != utterance.speaker:
                continue
            seconds = _overlap(utterance.span, emotion.span)
            if seconds <= 0:
                continue
            episodes.append(
                EmotionEpisode(
                    span=emotion.span,
                    speaker=emotion.speaker,
                    label=emotion.label,
                    score=emotion.score,
                    overlap_seconds=round(seconds, 3),
                    distribution={
                        label.name.lower(): score
                        for label, score in emotion.scores.items()
                    },
                )
            )
        return DialogueUtterance(
            span=utterance.span,
            speaker=utterance.speaker,
            text=utterance.text,
            speaker_overlap_seconds=utterance.speaker_overlap_seconds,
            speaker_coverage=utterance.speaker_coverage,
            word_count=utterance.word_count,
            mean_word_confidence=utterance.mean_word_confidence,
            emotion_episodes=tuple(episodes),
        )

    def _quality(self, utterances: tuple[DialogueUtterance, ...]) -> DialogueQuality:
        return DialogueQuality(
            utterances=len(utterances),
            unknown_speaker_utterances=sum(
                1 for item in utterances if item.speaker is None
            ),
            low_speaker_coverage_utterances=sum(
                1 for item in utterances if item.speaker_coverage < 0.5
            ),
            utterances_without_emotion=sum(
                1 for item in utterances if not item.emotion_episodes
            ),
        )


__all__ = ["DialogueAssembler"]
