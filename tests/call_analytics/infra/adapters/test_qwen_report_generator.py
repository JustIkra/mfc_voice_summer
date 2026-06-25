from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from call_analytics.infra.adapters.model_api import QwenReportGenerator, extract_json_object
from call_analytics.service import DialogueAssembler
from domain import (
    DiarizedSegment,
    DiarizedTranscript,
    EmotionAnalysis,
    EmotionLabel,
    RecordingId,
    Satisfaction,
    SegmentEmotion,
    SpeakerRole,
    TimeSpan,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)

RID = RecordingId("call-1")
NOW = datetime(2026, 6, 25, 12, 0, tzinfo=timezone(timedelta(hours=3)))


def span(start: float, end: float) -> TimeSpan:
    return TimeSpan(start=timedelta(seconds=start), end=timedelta(seconds=end))


def test_extract_json_object_rejects_reasoning_without_final_json() -> None:
    with pytest.raises(ValueError, match="does not contain final JSON"):
        extract_json_object({"content": None, "reasoning": '{"ok": true}'})


@pytest.mark.asyncio
async def test_qwen_report_prompt_contains_dialogue_and_keeps_thinking_enabled() -> None:
    captured: dict[str, Any] = {}

    async def fake_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {
            "choices": [
                {
                    "message": {
                        "reasoning_content": "analysis may exist",
                        "content": """
                        {
                          "file": "call-1.wav",
                          "client_speaker": "SPEAKER_01",
                          "operator_speaker": "SPEAKER_00",
                          "question_resolved": {
                            "value": "yes",
                            "confidence": 0.86,
                            "evidence": ["Клиент получил запись."]
                          },
                          "client_satisfaction": {
                            "value": "satisfied",
                            "score_1_5": 5,
                            "confidence": 0.8,
                            "evidence": ["Клиент поблагодарил оператора."]
                          },
                          "emotional_assessment": {
                            "overall": "Спокойный диалог.",
                            "client_emotions": ["happy"],
                            "operator_emotions": ["neutral"],
                            "evidence": ["SER happy на клиентской реплике."]
                          },
                          "summary": "Клиента записали на приём.",
                          "risks": [],
                          "recommendations": []
                        }
                        """,
                    }
                }
            ]
        }

    generator = QwenReportGenerator(
        base_url="http://qwen.local/v1",
        model="qwen3.6-35b",
        clock=lambda: NOW,
        assembler=DialogueAssembler(),
        post_json=fake_post_json,
    )
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(
            TranscriptSegment(
                span=span(0.0, 2.0),
                text="МФЦ здравствуйте хочу записаться",
                words=(
                    TranscriptWord(span=span(0.0, 0.5), text="МФЦ", confidence=0.99),
                    TranscriptWord(
                        span=span(0.5, 1.0),
                        text="здравствуйте",
                        confidence=0.98,
                    ),
                    TranscriptWord(span=span(1.2, 1.5), text="хочу", confidence=0.97),
                    TranscriptWord(
                        span=span(1.5, 2.0),
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
                span=span(0.0, 1.1),
                role=SpeakerRole.UNKNOWN,
                text="",
                speaker="SPEAKER_00",
            ),
            DiarizedSegment(
                span=span(1.1, 2.2),
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
                span=span(1.1, 2.2),
                role=SpeakerRole.UNKNOWN,
                speaker="SPEAKER_01",
                label=EmotionLabel.HAPPY,
                score=0.72,
                scores={EmotionLabel.HAPPY: 0.72},
            ),
        ),
    )

    report = await generator.generate(transcript, diarized, emotions)

    prompt = captured["payload"]["messages"][1]["content"]
    assert "speaker_coverage=" in prompt
    assert "emotions=" in prompt
    assert "Аудит качества разметки" in prompt
    assert captured["payload"]["max_tokens"] == 8192
    assert captured["payload"].get("chat_template_kwargs") is None
    assert captured["payload"].get("reasoning_effort") is None
    assert captured["timeout"] == 600
    assert report.satisfaction is Satisfaction.SATISFIED
    assert report.client_speaker == "SPEAKER_01"
    assert report.operator_speaker == "SPEAKER_00"
    assert report.question_resolved.value == "yes"
    assert report.client_satisfaction.score_1_5 == 5
