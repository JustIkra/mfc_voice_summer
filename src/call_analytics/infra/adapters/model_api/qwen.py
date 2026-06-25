from __future__ import annotations

import json
import re
import textwrap
import urllib.error
from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

from call_analytics.infra.http import PostJson, urllib_post_json
from call_analytics.service.ports import (
    DialogueAssemblerPort,
    ReportGenerator,
    ReportGeneratorError,
)
from domain import (
    CallReport,
    ClientSatisfaction,
    DiarizedTranscript,
    EmotionalAssessment,
    EmotionAnalysis,
    QuestionResolution,
    Satisfaction,
    SynchronizedDialogue,
    Transcript,
)


def extract_json_object(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError(f"Qwen response does not contain final JSON fields={sorted(message)}")
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        raise ValueError(f"Qwen response does not contain final JSON fields={sorted(message)}")
    return cast(dict[str, Any], json.loads(match.group(0)))


class QwenReportGenerator(ReportGenerator):
    def __init__(
        self,
        base_url: str,
        model: str,
        clock: Callable[[], datetime],
        assembler: DialogueAssemblerPort,
        post_json: PostJson = urllib_post_json,
        timeout_seconds: int = 600,
        max_tokens: int = 8192,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._clock = clock
        self._post_json = post_json
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._assembler = assembler

    async def generate(
        self,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> CallReport:
        dialogue = self._assembler.assemble(transcript, diarized, emotions)
        payload = {
            "model": self._model,
            "messages": self._messages(dialogue, transcript.recording_id.value),
            "temperature": 0.1,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            response = await self._post_json(
                f"{self._base_url}/chat/completions",
                payload,
                self._timeout_seconds,
            )
            raw_report = extract_json_object(response["choices"][0]["message"])
        except TimeoutError as error:
            raise ReportGeneratorError.timeout(str(error)) from error
        except urllib.error.URLError as error:
            raise ReportGeneratorError.connection(str(error)) from error
        except (KeyError, IndexError, json.JSONDecodeError, ValueError) as error:
            raise ReportGeneratorError.invalid_request(str(error)) from error
        return self._to_report(transcript.recording_id.value, raw_report)

    def _messages(
        self,
        dialogue: SynchronizedDialogue,
        recording_name: str,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Ты аналитик качества звонков МФЦ. Верни только валидный JSON "
                    "на русском языке. Не выдумывай факты: если данных недостаточно, "
                    "ставь unknown и объясняй почему. "
                    "SPEAKER_00/SPEAKER_01 — технические метки diarization, не роли. "
                    "Роли client_speaker/operator_speaker назначай только по смысловым "
                    "доказательствам."
                ),
            },
            {
                "role": "user",
                "content": textwrap.dedent(
                    f"""
                    Файл: {recording_name}.wav

                    Диалог. В каждой строке есть время, speaker diarization,
                    качество speaker_coverage,
                    средняя уверенность ASR asr_p, текст реплики и SER-эпизоды эмоций,
                    пересекающиеся именно с этой репликой:
                    {self._format_dialogue(dialogue)}

                    Аудит качества разметки:
                    {json.dumps(self._quality(dialogue), ensure_ascii=False)}

                    Сформируй JSON со строго такими полями:
                    {{
                      "file": "...",
                      "client_speaker": "SPEAKER_00|SPEAKER_01|unknown",
                      "operator_speaker": "SPEAKER_00|SPEAKER_01|unknown",
                      "question_resolved": {{
                        "value": "yes|no|partial|unknown",
                        "confidence": 0.0,
                        "evidence": ["..."]
                      }},
                      "client_satisfaction": {{
                        "value": "satisfied|neutral|dissatisfied|unknown",
                        "score_1_5": 0,
                        "confidence": 0.0,
                        "evidence": ["..."]
                      }},
                      "emotional_assessment": {{
                        "overall": "...",
                        "client_emotions": ["..."],
                        "operator_emotions": ["..."],
                        "evidence": ["..."]
                      }},
                      "summary": "...",
                      "risks": ["..."],
                      "recommendations": ["..."]
                    }}
                    """
                ).strip(),
            },
        ]

    def _format_dialogue(self, dialogue: SynchronizedDialogue) -> str:
        lines = []
        for item in dialogue.utterances:
            emotions = [
                {
                    "label": episode.label.name.lower(),
                    "score": episode.score,
                    "speaker": episode.speaker,
                    "overlap_seconds": episode.overlap_seconds,
                    "distribution": episode.distribution,
                }
                for episode in item.emotion_episodes
            ]
            lines.append(
                f"[{item.span.start.total_seconds():.1f}-{item.span.end.total_seconds():.1f}] "
                f"{item.speaker or 'UNKNOWN'} "
                f"speaker_coverage={item.speaker_coverage:.2f} "
                f"asr_p={item.mean_word_confidence}: {item.text} "
                f"| emotions={json.dumps(emotions, ensure_ascii=False)}"
            )
        return "\n".join(lines)

    def _quality(self, dialogue: SynchronizedDialogue) -> dict[str, int]:
        return {
            "utterances": dialogue.quality.utterances,
            "unknown_speaker_utterances": dialogue.quality.unknown_speaker_utterances,
            "low_speaker_coverage_utterances": dialogue.quality.low_speaker_coverage_utterances,
            "utterances_without_emotion": dialogue.quality.utterances_without_emotion,
        }

    def _to_report(self, recording_id: str, payload: dict[str, Any]) -> CallReport:
        satisfaction_payload = payload.get("client_satisfaction", {})
        resolution_payload = payload.get("question_resolved", {})
        emotional_payload = payload.get("emotional_assessment", {})
        return CallReport(
            recording_id=TranscriptIdAdapter(recording_id).recording_id,
            satisfaction=self._satisfaction(satisfaction_payload.get("value")),
            summary=str(payload.get("summary", "")),
            key_points=tuple(str(item) for item in payload.get("key_points", ())),
            generated_at=self._clock(),
            client_speaker=str(payload.get("client_speaker", "unknown")),
            operator_speaker=str(payload.get("operator_speaker", "unknown")),
            question_resolved=QuestionResolution(
                value=str(resolution_payload.get("value", "unknown")),
                confidence=float(resolution_payload.get("confidence", 0.0)),
                evidence=tuple(str(item) for item in resolution_payload.get("evidence", ())),
            ),
            client_satisfaction=ClientSatisfaction(
                value=str(satisfaction_payload.get("value", "unknown")),
                score_1_5=int(satisfaction_payload.get("score_1_5", 0)),
                confidence=float(satisfaction_payload.get("confidence", 0.0)),
                evidence=tuple(str(item) for item in satisfaction_payload.get("evidence", ())),
            ),
            emotional_assessment=EmotionalAssessment(
                overall=str(emotional_payload.get("overall", "unknown")),
                client_emotions=tuple(
                    str(item) for item in emotional_payload.get("client_emotions", ())
                ),
                operator_emotions=tuple(
                    str(item) for item in emotional_payload.get("operator_emotions", ())
                ),
                evidence=tuple(str(item) for item in emotional_payload.get("evidence", ())),
            ),
            risks=tuple(str(item) for item in payload.get("risks", ())),
            recommendations=tuple(str(item) for item in payload.get("recommendations", ())),
        )

    def _satisfaction(self, value: object) -> Satisfaction:
        if value == "satisfied":
            return Satisfaction.SATISFIED
        if value == "dissatisfied":
            return Satisfaction.DISSATISFIED
        return Satisfaction.NEUTRAL


class TranscriptIdAdapter:
    def __init__(self, value: str) -> None:
        from domain import RecordingId

        self.recording_id = RecordingId(value)


__all__ = ["QwenReportGenerator", "extract_json_object", "urllib_post_json"]
