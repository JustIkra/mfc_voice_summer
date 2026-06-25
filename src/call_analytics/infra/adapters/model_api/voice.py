from __future__ import annotations

import urllib.error
from typing import Any

from call_analytics.infra.http import PostJson, urllib_post_json
from call_analytics.service.ports import (
    EmotionRecognizer,
    EmotionRecognizerError,
    ModelAudioStager,
    SpeakerDiarizer,
    SpeakerDiarizerError,
    Transcriber,
    TranscriberError,
)
from domain import (
    AudioBlob,
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


class _VoiceModelClient:
    def __init__(
        self,
        base_url: str,
        audio_stager: ModelAudioStager,
        post_json: PostJson = urllib_post_json,
        timeout_seconds: int = 900,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._audio_stager = audio_stager
        self._post_json = post_json
        self._timeout_seconds = timeout_seconds

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post_json(
            f"{self._base_url}{endpoint}",
            payload,
            self._timeout_seconds,
        )


class VoiceModelTranscriber(_VoiceModelClient, Transcriber):
    async def transcribe(self, recording_id: RecordingId, audio: AudioBlob) -> Transcript:
        try:
            staged = await self._audio_stager.stage(recording_id, audio)
            payload = await self._post(
                "/transcribe",
                {"path": staged.path},
            )
        except ValueError as error:
            raise TranscriberError.invalid_format(str(error)) from error
        except TimeoutError as error:
            raise TranscriberError.timeout(str(error)) from error
        except urllib.error.URLError as error:
            raise TranscriberError.connection(str(error)) from error

        segments = tuple(self._segment(item) for item in payload.get("segments", ()))
        return Transcript(
            recording_id=recording_id,
            language=str(payload.get("language", "ru")),
            segments=segments,
            full_text=" ".join(segment.text for segment in segments).strip(),
        )

    def _segment(self, item: dict[str, Any]) -> TranscriptSegment:
        return TranscriptSegment(
            span=TimeSpan.from_seconds(float(item["start"]), float(item["end"])),
            text=str(item.get("text", "")).strip(),
            confidence=float(item.get("confidence", 1.0)),
            words=tuple(
                TranscriptWord(
                    span=TimeSpan.from_seconds(float(word["start"]), float(word["end"])),
                    text=str(word.get("word", "")).strip(),
                    confidence=float(word.get("probability", 1.0)),
                )
                for word in item.get("words", ())
                if str(word.get("word", "")).strip()
            ),
        )


class VoiceModelDiarizer(_VoiceModelClient, SpeakerDiarizer):
    async def diarize(
        self, audio: AudioBlob, transcript: Transcript
    ) -> DiarizedTranscript:
        try:
            staged = await self._audio_stager.stage(transcript.recording_id, audio)
            payload = await self._post(
                "/diarize",
                {"path": staged.path},
            )
        except ValueError as error:
            raise SpeakerDiarizerError.invalid_format(str(error)) from error
        except TimeoutError as error:
            raise SpeakerDiarizerError.timeout(str(error)) from error
        except urllib.error.URLError as error:
            raise SpeakerDiarizerError.connection(str(error)) from error

        return DiarizedTranscript(
            recording_id=transcript.recording_id,
            segments=tuple(
                DiarizedSegment(
                    span=TimeSpan.from_seconds(float(item["start"]), float(item["end"])),
                    role=SpeakerRole.UNKNOWN,
                    text="",
                    speaker=str(item.get("speaker")) if item.get("speaker") else None,
                )
                for item in payload.get("segments", ())
            ),
        )


class VoiceModelEmotionRecognizer(_VoiceModelClient, EmotionRecognizer):
    async def recognize(
        self, audio: AudioBlob, diarized: DiarizedTranscript
    ) -> EmotionAnalysis:
        try:
            staged = await self._audio_stager.stage(diarized.recording_id, audio)
            payload = await self._post(
                "/emotion",
                {
                    "path": staged.path,
                    "diarization": [
                        {
                            "start": segment.span.start.total_seconds(),
                            "end": segment.span.end.total_seconds(),
                            "speaker": segment.speaker,
                        }
                        for segment in diarized.segments
                    ],
                },
            )
        except ValueError as error:
            raise EmotionRecognizerError.invalid_format(str(error)) from error
        except TimeoutError as error:
            raise EmotionRecognizerError.timeout(str(error)) from error
        except urllib.error.URLError as error:
            raise EmotionRecognizerError.connection(str(error)) from error

        return EmotionAnalysis(
            recording_id=diarized.recording_id,
            segments=tuple(self._segment(item) for item in payload.get("segments", ())),
        )

    def _segment(self, item: dict[str, Any]) -> SegmentEmotion:
        scores = {
            self._label(label): float(score)
            for label, score in dict(item.get("distribution", {})).items()
        }
        label = self._label(str(item.get("label", "neutral")))
        return SegmentEmotion(
            span=TimeSpan.from_seconds(float(item["start"]), float(item["end"])),
            role=SpeakerRole.UNKNOWN,
            speaker=str(item.get("speaker")) if item.get("speaker") else None,
            label=label,
            score=float(item.get("score", scores.get(label, 1.0))),
            scores=scores,
        )

    def _label(self, value: str) -> EmotionLabel:
        normalized = value.strip().upper()
        mapping = {
            "NEUTRAL": EmotionLabel.NEUTRAL,
            "HAPPY": EmotionLabel.HAPPY,
            "ANGRY": EmotionLabel.ANGRY,
            "SAD": EmotionLabel.SAD,
            "SADNESS": EmotionLabel.SAD,
            "FEARFUL": EmotionLabel.FEARFUL,
            "FEAR": EmotionLabel.FEARFUL,
            "DISGUSTED": EmotionLabel.DISGUSTED,
            "DISGUST": EmotionLabel.DISGUSTED,
            "SURPRISED": EmotionLabel.SURPRISED,
            "SURPRISE": EmotionLabel.SURPRISED,
        }
        return mapping.get(normalized, EmotionLabel.NEUTRAL)


__all__ = [
    "VoiceModelDiarizer",
    "VoiceModelEmotionRecognizer",
    "VoiceModelTranscriber",
]
