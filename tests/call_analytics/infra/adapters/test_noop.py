from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.noop import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)
from domain import (
    AudioBlob,
    ChannelLayout,
    DiarizedTranscript,
    EmotionAnalysis,
    RecordingId,
    SpeakerRole,
    TimeSpan,
    Transcript,
    TranscriptSegment,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
RID = RecordingId("rec-1")


async def test_noop_transcriber_returns_deterministic_transcript() -> None:
    blob = AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)
    tr = await NoopTranscriber(RID).transcribe(RID, blob)
    assert isinstance(tr, Transcript)
    assert tr.recording_id == RID
    assert tr.segments


async def test_noop_diarizer_maps_channel_to_role() -> None:
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(
            TranscriptSegment(
                TimeSpan(timedelta(0), timedelta(seconds=1)), "оператор", channel=0
            ),
            TranscriptSegment(
                TimeSpan(timedelta(seconds=1), timedelta(seconds=2)), "клиент", channel=1
            ),
            TranscriptSegment(
                TimeSpan(timedelta(seconds=2), timedelta(seconds=3)), "?", channel=None
            ),
        ),
        full_text="оператор клиент ?",
    )
    blob = AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)
    dt = await NoopDiarizer().diarize(blob, transcript)
    assert isinstance(dt, DiarizedTranscript)
    roles = [s.role for s in dt.segments]
    assert roles == [SpeakerRole.OPERATOR, SpeakerRole.CLIENT, SpeakerRole.UNKNOWN]


async def test_noop_emotion_is_neutral_per_segment() -> None:
    dt = DiarizedTranscript(recording_id=RID, segments=())
    ea = await NoopEmotionRecognizer().recognize(
        AudioBlob(b"x", "wav", ChannelLayout.MONO), dt
    )
    assert isinstance(ea, EmotionAnalysis)
    assert ea.recording_id == RID


async def test_noop_report_generator_builds_report() -> None:
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(),
        full_text="",
    )
    dt = DiarizedTranscript(recording_id=RID, segments=())
    ea = EmotionAnalysis(recording_id=RID, segments=())
    generated_at = datetime(2026, 1, 10, tzinfo=MSK)
    report = await NoopReportGenerator(generated_at=generated_at).generate(transcript, dt, ea)
    assert report.recording_id == RID
    assert report.summary
