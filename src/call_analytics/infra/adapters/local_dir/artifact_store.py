from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from call_analytics.infra.ports import ArtifactStore
from domain import (
    CallRecording,
    CallReport,
    ChannelLayout,
    ClientSatisfaction,
    DiarizedSegment,
    DiarizedTranscript,
    EmotionalAssessment,
    EmotionAnalysis,
    EmotionLabel,
    QuestionResolution,
    RecordingId,
    Satisfaction,
    SegmentEmotion,
    SpeakerRole,
    TimeSpan,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)


class LocalArtifactStore(ArtifactStore):
    def __init__(self, root: Path) -> None:
        self._root = root

    async def save_recording(self, recording: CallRecording) -> None:
        self._write_json(
            self._artifact_path("recordings", recording.id, ".recording.json"),
            {
                "id": recording.id.value,
                "started_at": recording.started_at.isoformat(),
                "duration_seconds": recording.duration.total_seconds(),
                "channel_layout": recording.channel_layout.name,
                "operator_id": recording.operator_id,
                "metadata": dict(recording.metadata),
            },
        )

    async def load_recording(self, recording_id: RecordingId) -> CallRecording | None:
        payload = self._read_json(
            self._artifact_path("recordings", recording_id, ".recording.json")
        )
        if payload is None:
            return None
        return CallRecording(
            id=recording_id,
            started_at=datetime.fromisoformat(str(payload["started_at"])),
            duration=timedelta(seconds=float(payload["duration_seconds"])),
            channel_layout=ChannelLayout[str(payload["channel_layout"])],
            operator_id=payload.get("operator_id"),
            metadata=dict(payload.get("metadata", {})),
        )

    async def save_transcript(self, transcript: Transcript) -> None:
        self._write_json(
            self._artifact_path("transcripts", transcript.recording_id, ".transcript.json"),
            {
                "recording_id": transcript.recording_id.value,
                "language": transcript.language,
                "full_text": transcript.full_text,
                "segments": [
                    self._transcript_segment_to_json(item)
                    for item in transcript.segments
                ],
            },
        )

    async def load_transcript(self, recording_id: RecordingId) -> Transcript | None:
        payload = self._read_json(
            self._artifact_path("transcripts", recording_id, ".transcript.json")
        )
        if payload is None:
            return None
        return Transcript(
            recording_id=recording_id,
            language=str(payload["language"]),
            segments=tuple(
                self._transcript_segment_from_json(item)
                for item in payload["segments"]
            ),
            full_text=str(payload["full_text"]),
        )

    async def save_diarization(self, diarized: DiarizedTranscript) -> None:
        self._write_json(
            self._artifact_path("diarization", diarized.recording_id, ".diarization.json"),
            {
                "recording_id": diarized.recording_id.value,
                "segments": [self._diarized_segment_to_json(item) for item in diarized.segments],
            },
        )

    async def load_diarization(self, recording_id: RecordingId) -> DiarizedTranscript | None:
        payload = self._read_json(
            self._artifact_path("diarization", recording_id, ".diarization.json")
        )
        if payload is None:
            return None
        return DiarizedTranscript(
            recording_id=recording_id,
            segments=tuple(self._diarized_segment_from_json(item) for item in payload["segments"]),
        )

    async def save_emotion(self, emotion: EmotionAnalysis) -> None:
        self._write_json(
            self._artifact_path("emotions", emotion.recording_id, ".emotion.json"),
            {
                "recording_id": emotion.recording_id.value,
                "segments": [self._emotion_segment_to_json(item) for item in emotion.segments],
            },
        )

    async def load_emotion(self, recording_id: RecordingId) -> EmotionAnalysis | None:
        payload = self._read_json(self._artifact_path("emotions", recording_id, ".emotion.json"))
        if payload is None:
            return None
        return EmotionAnalysis(
            recording_id=recording_id,
            segments=tuple(self._emotion_segment_from_json(item) for item in payload["segments"]),
        )

    async def save_report(self, report: CallReport) -> None:
        self._write_json(
            self._artifact_path("reports", report.recording_id, ".report.json"),
            self._report_to_json(report),
        )

    async def load_report(self, recording_id: RecordingId) -> CallReport | None:
        payload = self._read_json(self._artifact_path("reports", recording_id, ".report.json"))
        if payload is None:
            return None
        return self._report_from_json(recording_id, payload)

    async def save_report_pdf(self, recording_id: RecordingId, content: bytes) -> None:
        path = self._artifact_path("reports", recording_id, ".pdf")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    async def load_report_pdf(self, recording_id: RecordingId) -> bytes | None:
        path = self._artifact_path("reports", recording_id, ".pdf")
        if not path.is_file():
            return None
        return path.read_bytes()

    def _artifact_path(self, directory: str, recording_id: RecordingId, suffix: str) -> Path:
        return self._root / directory / f"{recording_id.value}{suffix}"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    def _span_to_json(self, span: TimeSpan) -> dict[str, float]:
        return {"start": span.start.total_seconds(), "end": span.end.total_seconds()}

    def _span_from_json(self, payload: dict[str, Any]) -> TimeSpan:
        return TimeSpan.from_seconds(float(payload["start"]), float(payload["end"]))

    def _transcript_segment_to_json(self, segment: TranscriptSegment) -> dict[str, Any]:
        return {
            "span": self._span_to_json(segment.span),
            "text": segment.text,
            "channel": segment.channel,
            "confidence": segment.confidence,
            "words": [
                {
                    "span": self._span_to_json(word.span),
                    "text": word.text,
                    "confidence": word.confidence,
                }
                for word in segment.words
            ],
        }

    def _transcript_segment_from_json(self, payload: dict[str, Any]) -> TranscriptSegment:
        return TranscriptSegment(
            span=self._span_from_json(payload["span"]),
            text=str(payload["text"]),
            channel=payload.get("channel"),
            confidence=float(payload.get("confidence", 1.0)),
            words=tuple(
                TranscriptWord(
                    span=self._span_from_json(word["span"]),
                    text=str(word["text"]),
                    confidence=float(word.get("confidence", 1.0)),
                )
                for word in payload.get("words", ())
            ),
        )

    def _diarized_segment_to_json(self, segment: DiarizedSegment) -> dict[str, Any]:
        return {
            "span": self._span_to_json(segment.span),
            "role": segment.role.name,
            "text": segment.text,
            "speaker": segment.speaker,
            "speaker_overlap_seconds": segment.speaker_overlap_seconds,
            "speaker_coverage": segment.speaker_coverage,
        }

    def _diarized_segment_from_json(self, payload: dict[str, Any]) -> DiarizedSegment:
        return DiarizedSegment(
            span=self._span_from_json(payload["span"]),
            role=SpeakerRole[str(payload["role"])],
            text=str(payload["text"]),
            speaker=payload.get("speaker"),
            speaker_overlap_seconds=float(payload.get("speaker_overlap_seconds", 0.0)),
            speaker_coverage=float(payload.get("speaker_coverage", 0.0)),
        )

    def _emotion_segment_to_json(self, segment: SegmentEmotion) -> dict[str, Any]:
        return {
            "span": self._span_to_json(segment.span),
            "role": segment.role.name,
            "speaker": segment.speaker,
            "label": segment.label.name,
            "score": segment.score,
            "scores": {label.name: score for label, score in segment.scores.items()},
        }

    def _emotion_segment_from_json(self, payload: dict[str, Any]) -> SegmentEmotion:
        return SegmentEmotion(
            span=self._span_from_json(payload["span"]),
            role=SpeakerRole[str(payload["role"])],
            speaker=payload.get("speaker"),
            label=EmotionLabel[str(payload["label"])],
            score=float(payload.get("score", 1.0)),
            scores={
                EmotionLabel[str(label)]: float(score)
                for label, score in dict(payload.get("scores", {})).items()
            },
        )

    def _report_to_json(self, report: CallReport) -> dict[str, Any]:
        return {
            "recording_id": report.recording_id.value,
            "satisfaction": report.satisfaction.name,
            "summary": report.summary,
            "key_points": list(report.key_points),
            "generated_at": report.generated_at.isoformat(),
            "question_resolved": {
                "value": report.question_resolved.value,
                "confidence": report.question_resolved.confidence,
                "evidence": list(report.question_resolved.evidence),
            },
            "client_satisfaction": {
                "value": report.client_satisfaction.value,
                "score_1_5": report.client_satisfaction.score_1_5,
                "confidence": report.client_satisfaction.confidence,
                "evidence": list(report.client_satisfaction.evidence),
            },
            "emotional_assessment": {
                "overall": report.emotional_assessment.overall,
                "client_emotions": list(report.emotional_assessment.client_emotions),
                "operator_emotions": list(report.emotional_assessment.operator_emotions),
                "evidence": list(report.emotional_assessment.evidence),
            },
            "risks": list(report.risks),
            "recommendations": list(report.recommendations),
        }

    def _report_from_json(self, recording_id: RecordingId, payload: dict[str, Any]) -> CallReport:
        question = payload["question_resolved"]
        satisfaction = payload["client_satisfaction"]
        emotional = payload["emotional_assessment"]
        return CallReport(
            recording_id=recording_id,
            satisfaction=Satisfaction[str(payload["satisfaction"])],
            summary=str(payload["summary"]),
            key_points=tuple(str(item) for item in payload.get("key_points", ())),
            generated_at=datetime.fromisoformat(str(payload["generated_at"])),
            question_resolved=QuestionResolution(
                value=str(question["value"]),
                confidence=float(question["confidence"]),
                evidence=tuple(str(item) for item in question.get("evidence", ())),
            ),
            client_satisfaction=ClientSatisfaction(
                value=str(satisfaction["value"]),
                score_1_5=int(satisfaction["score_1_5"]),
                confidence=float(satisfaction["confidence"]),
                evidence=tuple(str(item) for item in satisfaction.get("evidence", ())),
            ),
            emotional_assessment=EmotionalAssessment(
                overall=str(emotional["overall"]),
                client_emotions=tuple(str(item) for item in emotional.get("client_emotions", ())),
                operator_emotions=tuple(
                    str(item) for item in emotional.get("operator_emotions", ())
                ),
                evidence=tuple(str(item) for item in emotional.get("evidence", ())),
            ),
            risks=tuple(str(item) for item in payload.get("risks", ())),
            recommendations=tuple(str(item) for item in payload.get("recommendations", ())),
        )


__all__ = ["LocalArtifactStore"]
