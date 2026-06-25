from __future__ import annotations

import urllib.error
from dataclasses import fields
from datetime import timedelta
from typing import Any

import pytest

from call_analytics.infra.adapters.model_api import (
    MountedDirectoryAudioStager,
    VoiceModelDiarizer,
    VoiceModelEmotionRecognizer,
    VoiceModelTranscriber,
)
from call_analytics.service.ports import (
    ModelAudio,
    ModelAudioStager,
    SpeakerDiarizerError,
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


class FakeAudioStager(ModelAudioStager):
    def __init__(self) -> None:
        self.calls: list[tuple[RecordingId, bytes]] = []

    async def stage(self, recording_id: RecordingId, audio: AudioBlob) -> ModelAudio:
        self.calls.append((recording_id, audio.data))
        return ModelAudio(path=f"/data/staged/{recording_id.value}.wav")


class BuggyAudioStager(ModelAudioStager):
    async def stage(self, recording_id: RecordingId, audio: AudioBlob) -> ModelAudio:
        raise AssertionError("bug in stager")


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
        audio_stager=FakeAudioStager(),
    )
    audio = AudioBlob(
        data=b"x",
        codec="wav",
        layout=ChannelLayout.STEREO,
    )

    transcript = await transcriber.transcribe(RID, audio)

    assert captured["payload"] == {"path": "/data/staged/call-1.wav"}
    assert transcript.recording_id == RID
    assert transcript.segments[0].words[1].text == "здравствуйте"
    assert transcript.full_text == "МФЦ здравствуйте"


async def test_transcriber_uses_explicit_audio_stager_contract() -> None:
    captured: dict[str, Any] = {}
    stager = FakeAudioStager()

    async def fake_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        captured["payload"] = payload
        return {"language": "ru", "segments": []}

    transcriber = VoiceModelTranscriber(
        base_url="http://asr.local",
        post_json=fake_post_json,
        audio_stager=stager,
    )
    audio = AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)

    await transcriber.transcribe(RID, audio)

    assert stager.calls == [(RID, b"x")]
    assert captured["payload"] == {"path": "/data/staged/call-1.wav"}


async def test_mounted_directory_audio_stager_writes_blob_and_returns_model_path(tmp_path) -> None:
    stager = MountedDirectoryAudioStager(
        host_directory=tmp_path,
        model_directory="/data/recordings",
    )

    staged = await stager.stage(
        RID,
        AudioBlob(data=b"wav-bytes", codec="wav", layout=ChannelLayout.STEREO),
    )

    assert (tmp_path / "call-1.wav").read_bytes() == b"wav-bytes"
    assert staged.path == "/data/recordings/call-1.wav"


async def test_audio_blob_does_not_expose_infrastructure_source_path() -> None:
    assert "source_path" not in {field.name for field in fields(AudioBlob)}


async def test_transcriber_does_not_mask_stager_programming_error() -> None:
    async def fake_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        return {"language": "ru", "segments": []}

    transcriber = VoiceModelTranscriber(
        base_url="http://asr.local",
        post_json=fake_post_json,
        audio_stager=BuggyAudioStager(),
    )

    with pytest.raises(AssertionError, match="bug in stager"):
        await transcriber.transcribe(
            RID,
            AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO),
        )


async def test_transcriber_does_not_mask_transport_programming_error() -> None:
    async def buggy_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        raise AssertionError("bug in transport")

    transcriber = VoiceModelTranscriber(
        base_url="http://asr.local",
        post_json=buggy_post_json,
        audio_stager=FakeAudioStager(),
    )

    with pytest.raises(AssertionError, match="bug in transport"):
        await transcriber.transcribe(
            RID,
            AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO),
        )


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
        audio_stager=FakeAudioStager(),
    )
    audio = AudioBlob(
        data=b"x",
        codec="wav",
        layout=ChannelLayout.STEREO,
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


async def test_diarizer_maps_transport_connection_error() -> None:
    async def failing_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        raise urllib.error.URLError("connection refused")

    diarizer = VoiceModelDiarizer(
        base_url="http://diar.local",
        post_json=failing_post_json,
        audio_stager=FakeAudioStager(),
    )
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(TranscriptSegment(span=span(0.0, 2.0), text="текст"),),
        full_text="текст",
    )

    with pytest.raises(SpeakerDiarizerError) as error:
        await diarizer.diarize(
            AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO),
            transcript,
        )

    assert error.value.kind is SpeakerDiarizerError.Kind.CONNECTION


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
        audio_stager=FakeAudioStager(),
    )
    audio = AudioBlob(
        data=b"x",
        codec="wav",
        layout=ChannelLayout.STEREO,
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
