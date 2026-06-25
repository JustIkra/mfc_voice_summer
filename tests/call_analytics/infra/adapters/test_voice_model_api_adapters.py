from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from call_analytics.infra.adapters.model_api import (
    VoiceModelDiarizer,
    VoiceModelEmotionRecognizer,
    VoiceModelTranscriber,
)
from domain import (
    AudioBlob,
    ChannelLayout,
    DiarizedSegment,
    DiarizedTranscript,
    EmotionLabel,
    RecordingId,
    SpeakerRole,
    TimeSpan,
    Transcript,
    TranscriptSegment,
)

pytestmark = pytest.mark.asyncio
RID = RecordingId("call-1")


def span(start: float, end: float) -> TimeSpan:
    return TimeSpan(start=timedelta(seconds=start), end=timedelta(seconds=end))


async def test_transcriber_maps_model_api_segments_and_words() -> None:
    captured: dict[str, Any] = {}

    async def fake_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        return {
            "language": "ru",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "МФЦ здравствуйте",
                    "words": [
                        {"start": 0.0, "end": 0.4, "word": "МФЦ", "probability": 0.99},
                        {
                            "start": 0.4,
                            "end": 1.0,
                            "word": "здравствуйте",
                            "probability": 0.98,
                        },
                    ],
                }
            ],
        }

    transcriber = VoiceModelTranscriber(
        base_url="http://asr.local",
        post_json=fake_post_json,
        container_recordings_dir="/data/recordings",
    )
    audio = AudioBlob(
        data=b"x",
        codec="wav",
        layout=ChannelLayout.STEREO,
        source_path="/host/recordings/call-1.wav",
    )

    transcript = await transcriber.transcribe(RID, audio)

    assert captured["payload"] == {"path": "/data/recordings/call-1.wav"}
    assert transcript.recording_id == RID
    assert transcript.segments[0].words[1].text == "здравствуйте"
    assert transcript.full_text == "МФЦ здравствуйте"


async def test_diarizer_maps_speaker_segments_without_collapsing_to_roles() -> None:
    async def fake_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        return {
            "segments": [
                {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
                {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
            ]
        }

    diarizer = VoiceModelDiarizer(
        base_url="http://diar.local",
        post_json=fake_post_json,
        container_recordings_dir="/data/recordings",
    )
    audio = AudioBlob(
        data=b"x",
        codec="wav",
        layout=ChannelLayout.STEREO,
        source_path="/host/recordings/call-1.wav",
    )
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(TranscriptSegment(span=span(0.0, 2.0), text="текст"),),
        full_text="текст",
    )

    diarized = await diarizer.diarize(audio, transcript)

    assert [segment.speaker for segment in diarized.segments] == ["SPEAKER_00", "SPEAKER_01"]
    assert all(segment.role is SpeakerRole.UNKNOWN for segment in diarized.segments)


async def test_emotion_recognizer_maps_segment_emotions_with_speaker_labels() -> None:
    async def fake_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        return {
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "speaker": "SPEAKER_01",
                    "label": "angry",
                    "score": 0.7,
                    "distribution": {"angry": 0.7, "neutral": 0.3},
                }
            ]
        }

    recognizer = VoiceModelEmotionRecognizer(
        base_url="http://emotion.local",
        post_json=fake_post_json,
        container_recordings_dir="/data/recordings",
    )
    audio = AudioBlob(
        data=b"x",
        codec="wav",
        layout=ChannelLayout.STEREO,
        source_path="/host/recordings/call-1.wav",
    )
    diarized = DiarizedTranscript(
        recording_id=RID,
        segments=(
            DiarizedSegment(
                span=span(0.0, 1.0),
                role=SpeakerRole.UNKNOWN,
                text="",
                speaker="SPEAKER_01",
            ),
        ),
    )

    emotions = await recognizer.recognize(audio, diarized)

    assert emotions.segments[0].speaker == "SPEAKER_01"
    assert emotions.segments[0].label is EmotionLabel.ANGRY
    assert emotions.segments[0].scores[EmotionLabel.ANGRY] == 0.7
