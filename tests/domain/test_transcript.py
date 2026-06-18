from datetime import timedelta

from domain.recording import RecordingId
from domain.transcript import TimeSpan, Transcript, TranscriptSegment


def test_transcript_holds_segments() -> None:
    seg = TranscriptSegment(
        span=TimeSpan(start=timedelta(0), end=timedelta(seconds=2)),
        text="алло",
        channel=0,
        confidence=0.9,
    )
    tr = Transcript(
        recording_id=RecordingId("rec-1"),
        language="ru",
        segments=(seg,),
        full_text="алло",
    )
    assert tr.segments[0].channel == 0
    assert tr.full_text == "алло"
