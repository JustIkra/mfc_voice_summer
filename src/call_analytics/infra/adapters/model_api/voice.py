from __future__ import annotations

import urllib.error
from pathlib import Path
from typing import Any

from call_analytics.infra.adapters.model_api.qwen import PostJson, urllib_post_json
from call_analytics.infra.ports import (
    EmotionRecognizer,
    EmotionRecognizerError,
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
        post_json: PostJson = urllib_post_json,
        timeout_seconds: int = 900,
        container_recordings_dir: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._post_json = post_json
        self._timeout_seconds = timeout_seconds
        self._container_recordings_dir = container_recordings_dir

    def _audio_path(self, audio: AudioBlob) -> str:
        if audio.source_path is None:
            raise ValueError("AudioBlob.source_path is required for model API adapters")
        path = Path(audio.source_path)
        if self._container_recordings_dir is not None:
            return str(Path(self._container_recordings_dir) / path.name)
        return str(path)

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post_json(
            f"{self._base_url}{endpoint}",
            payload,
            self._timeout_seconds,
        )


class VoiceModelTranscriber(_VoiceModelClient, Transcriber):
    async def transcribe(self, recording_id: RecordingId, audio: AudioBlob) -> Transcript:
        try:
            payload = await self._post("/transcribe", {"path": self._audio_path(audio)})
        except ValueError as error:
            raise TranscriberError.invalid_format(str(error)) from error
        except TimeoutError as error:
            raise TranscriberError.timeout(str(error)) from error
        except urllib.error.URLError as error:
            raise TranscriberError.connection(str(error)) from error
        except Exception as error:
            raise TranscriberError.unexpected(str(error)) from error

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
            payload = await self._post("/diarize", {"path": self._audio_path(audio)})
        except ValueError as error:
            raise SpeakerDiarizerError.invalid_format(str(error)) from error
        except TimeoutError as error:
            raise SpeakerDiarizerError.timeout(str(error)) from error
        except Exception as error:
            raise SpeakerDiarizerError.unexpected(str(error)) from error

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
            payload = await self._post(
                "/emotion",
                {
                    "path": self._audio_path(audio),
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
        except Exception as error:
            raise EmotionRecognizerError.unexpected(str(error)) from error

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
