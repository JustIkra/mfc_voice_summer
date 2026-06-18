from datetime import timedelta

from domain.diarization import DiarizedSegment, DiarizedTranscript, SpeakerRole
from domain.recording import RecordingId
from domain.transcript import TimeSpan


def test_diarized_transcript_tags_roles() -> None:
    seg = DiarizedSegment(
        span=TimeSpan(start=timedelta(0), end=timedelta(seconds=2)),
        role=SpeakerRole.OPERATOR,
        text="здравствуйте",
    )
    dt = DiarizedTranscript(recording_id=RecordingId("rec-1"), segments=(seg,))
    assert dt.segments[0].role is SpeakerRole.OPERATOR
