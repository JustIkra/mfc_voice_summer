# Пайплайн анализа звонков (Naumen) — план реализации скелета

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собрать скелет clean-architecture пайплайна обработки звонков (домен + порты инфра-уровня + сервис-оркестратор со машиной состояний job + noop/in_memory адаптеры), на котором позже навешиваются реальные адаптеры (Naumen, faster-whisper, SER, qwen).

**Architecture:** Ports & adapters / dependency inversion. `domain` — чистые `@dataclass(frozen=True, slots=True)` без инфра-зависимостей. Инфра-абстракции — `abc.ABC` порты с контрактными ошибками `<Port>Error(Kind)`. `service` оркестрирует стадии TRANSCRIBE→DIARIZE→EMOTION→REPORT поверх портов, состояние держит доменный агрегат `CallProcessingJob`. Границы пакетов фиксируются через `__all__` в `__init__.py` (OCP).

**Tech Stack:** Python 3.12, uv, pytest + pytest-asyncio (`asyncio_mode=auto`), ruff (line-length 100), mypy. Раскладка как в референсе `Knowleage_base_for_kyrsk`: `pythonpath=["src"]`.

**Spec:** `.memory-base/specs/2026-06-18-call-analytics-pipeline-design.md`

**Конвенции:** докстринги на русском; комментариев в коде нет; везде `from __future__ import annotations`; импорты потребителей — только с границы пакета (`from domain import ...`, `from call_analytics.infra.ports import ...`).

---

## Карта файлов

```
pyproject.toml                                  # tooling, deps
src/domain/__init__.py                          # граница: re-export моделей
src/domain/recording.py                         # RecordingId, ChannelLayout, AudioBlob, CallRecording
src/domain/transcript.py                        # TimeSpan, TranscriptSegment, Transcript
src/domain/diarization.py                       # SpeakerRole, DiarizedSegment, DiarizedTranscript
src/domain/emotion.py                           # EmotionLabel, SegmentEmotion, EmotionAnalysis
src/domain/report.py                            # Satisfaction, CallReport
src/domain/errors.py                            # InvalidJobTransition
src/domain/job.py                               # JobStage, JobStatus, CallProcessingJob, STAGE_ORDER
src/call_analytics/__init__.py
src/call_analytics/infra/__init__.py
src/call_analytics/infra/ports/__init__.py      # граница: re-export портов и *Error
src/call_analytics/infra/ports/recording_source.py
src/call_analytics/infra/ports/transcriber.py
src/call_analytics/infra/ports/diarizer.py
src/call_analytics/infra/ports/emotion_recognizer.py
src/call_analytics/infra/ports/report_generator.py
src/call_analytics/infra/ports/job_repository.py
src/call_analytics/infra/ports/artifact_store.py
src/call_analytics/infra/adapters/__init__.py
src/call_analytics/infra/adapters/noop/__init__.py
src/call_analytics/infra/adapters/in_memory/__init__.py
src/call_analytics/service/__init__.py          # граница: CallProcessingService
src/call_analytics/service/ports/__init__.py    # граница: CallProcessingPipeline
src/call_analytics/service/ports/pipeline.py
src/call_analytics/service/pipeline.py
tests/...                                        # зеркало по модулям
```

---

### Task 1: Каркас проекта и тулинг

**Files:**
- Create: `pyproject.toml`
- Create: `src/domain/__init__.py` (пустой пока)
- Create: `tests/__init__.py` (пустой)
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Инициализировать git и создать `pyproject.toml`**

Create `pyproject.toml`:

```toml
[project]
name = "mfc-voice-summer"
version = "0.1.0"
description = "Пайплайн анализа звонков ИИ колл-центра (Naumen)"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
    "mypy>=1.10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/domain", "src/call_analytics"]
sources = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]
ignore = ["RUF001", "RUF002", "RUF003"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Создать пустые пакеты-границы**

Create `src/domain/__init__.py` with content:

```python
from __future__ import annotations
```

Create `tests/__init__.py` (empty file).

- [ ] **Step 3: Написать smoke-тест**

Create `tests/test_smoke.py`:

```python
def test_smoke() -> None:
    assert True
```

- [ ] **Step 4: Установить окружение и запустить тест**

Run:
```bash
cd /Users/maksim/git_projects/mfc_voice_summer
git init
uv venv
uv pip install -e ".[dev]"
uv run pytest tests/test_smoke.py -v
```
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/domain/__init__.py tests/__init__.py tests/test_smoke.py .gitignore
git commit -m "chore: scaffold project, tooling, smoke test"
```

(Если `.gitignore` ещё нет — создать с `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`.)

---

### Task 2: Домен — recording.py

**Files:**
- Create: `src/domain/recording.py`
- Test: `tests/domain/test_recording.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/domain/__init__.py` (empty), затем `tests/domain/test_recording.py`:

```python
from datetime import datetime, timedelta, timezone

from domain.recording import AudioBlob, CallRecording, ChannelLayout, RecordingId

MSK = timezone(timedelta(hours=3))


def test_recording_is_immutable_value() -> None:
    rec = CallRecording(
        id=RecordingId("rec-1"),
        started_at=datetime(2026, 1, 10, 12, 0, tzinfo=MSK),
        duration=timedelta(minutes=5),
        channel_layout=ChannelLayout.STEREO,
    )
    assert rec.id == RecordingId("rec-1")
    assert rec.operator_id is None
    assert dict(rec.metadata) == {}


def test_audio_blob_carries_layout() -> None:
    blob = AudioBlob(data=b"\x00", codec="wav/gsm0610", layout=ChannelLayout.MONO)
    assert blob.layout is ChannelLayout.MONO
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/domain/test_recording.py -v`
Expected: FAIL (ModuleNotFoundError: domain.recording).

- [ ] **Step 3: Реализовать**

Create `src/domain/recording.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any


@dataclass(frozen=True, slots=True)
class RecordingId:
    value: str


class ChannelLayout(Enum):
    MONO = auto()
    STEREO = auto()


@dataclass(frozen=True, slots=True)
class AudioBlob:
    data: bytes
    codec: str
    layout: ChannelLayout


@dataclass(frozen=True, slots=True)
class CallRecording:
    id: RecordingId
    started_at: datetime
    duration: timedelta
    channel_layout: ChannelLayout
    operator_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = ["AudioBlob", "CallRecording", "ChannelLayout", "RecordingId"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/domain/test_recording.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/domain/recording.py tests/domain/
git commit -m "feat(domain): recording value objects"
```

---

### Task 3: Домен — transcript.py

**Files:**
- Create: `src/domain/transcript.py`
- Test: `tests/domain/test_transcript.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/domain/test_transcript.py`:

```python
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/domain/test_transcript.py -v`
Expected: FAIL (ModuleNotFoundError: domain.transcript).

- [ ] **Step 3: Реализовать**

Create `src/domain/transcript.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from domain.recording import RecordingId


@dataclass(frozen=True, slots=True)
class TimeSpan:
    start: timedelta
    end: timedelta


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    span: TimeSpan
    text: str
    channel: int | None = None
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class Transcript:
    recording_id: RecordingId
    language: str
    segments: tuple[TranscriptSegment, ...]
    full_text: str


__all__ = ["TimeSpan", "Transcript", "TranscriptSegment"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/domain/test_transcript.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/domain/transcript.py tests/domain/test_transcript.py
git commit -m "feat(domain): transcript model"
```

---

### Task 4: Домен — diarization.py

**Files:**
- Create: `src/domain/diarization.py`
- Test: `tests/domain/test_diarization.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/domain/test_diarization.py`:

```python
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/domain/test_diarization.py -v`
Expected: FAIL (ModuleNotFoundError: domain.diarization).

- [ ] **Step 3: Реализовать**

Create `src/domain/diarization.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from domain.recording import RecordingId
from domain.transcript import TimeSpan


class SpeakerRole(Enum):
    OPERATOR = auto()
    CLIENT = auto()
    UNKNOWN = auto()


@dataclass(frozen=True, slots=True)
class DiarizedSegment:
    span: TimeSpan
    role: SpeakerRole
    text: str


@dataclass(frozen=True, slots=True)
class DiarizedTranscript:
    recording_id: RecordingId
    segments: tuple[DiarizedSegment, ...]


__all__ = ["DiarizedSegment", "DiarizedTranscript", "SpeakerRole"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/domain/test_diarization.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/domain/diarization.py tests/domain/test_diarization.py
git commit -m "feat(domain): diarization model"
```

---

### Task 5: Домен — emotion.py

**Files:**
- Create: `src/domain/emotion.py`
- Test: `tests/domain/test_emotion.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/domain/test_emotion.py`:

```python
from datetime import timedelta

from domain.diarization import SpeakerRole
from domain.emotion import EmotionAnalysis, EmotionLabel, SegmentEmotion
from domain.recording import RecordingId
from domain.transcript import TimeSpan


def test_emotion_analysis_holds_scores() -> None:
    se = SegmentEmotion(
        span=TimeSpan(start=timedelta(0), end=timedelta(seconds=2)),
        role=SpeakerRole.CLIENT,
        label=EmotionLabel.ANGRY,
        scores={EmotionLabel.ANGRY: 0.8, EmotionLabel.NEUTRAL: 0.2},
    )
    ea = EmotionAnalysis(recording_id=RecordingId("rec-1"), segments=(se,))
    assert ea.segments[0].label is EmotionLabel.ANGRY
    assert ea.segments[0].scores[EmotionLabel.ANGRY] == 0.8
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/domain/test_emotion.py -v`
Expected: FAIL (ModuleNotFoundError: domain.emotion).

- [ ] **Step 3: Реализовать**

Create `src/domain/emotion.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto

from domain.diarization import SpeakerRole
from domain.recording import RecordingId
from domain.transcript import TimeSpan


class EmotionLabel(Enum):
    NEUTRAL = auto()
    HAPPY = auto()
    ANGRY = auto()
    SAD = auto()
    FEARFUL = auto()
    DISGUSTED = auto()
    SURPRISED = auto()


@dataclass(frozen=True, slots=True)
class SegmentEmotion:
    span: TimeSpan
    role: SpeakerRole
    label: EmotionLabel
    scores: Mapping[EmotionLabel, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmotionAnalysis:
    recording_id: RecordingId
    segments: tuple[SegmentEmotion, ...]


__all__ = ["EmotionAnalysis", "EmotionLabel", "SegmentEmotion"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/domain/test_emotion.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/domain/emotion.py tests/domain/test_emotion.py
git commit -m "feat(domain): emotion model"
```

---

### Task 6: Домен — report.py

**Files:**
- Create: `src/domain/report.py`
- Test: `tests/domain/test_report.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/domain/test_report.py`:

```python
from datetime import datetime, timedelta, timezone

from domain.recording import RecordingId
from domain.report import CallReport, Satisfaction

MSK = timezone(timedelta(hours=3))


def test_call_report_summarizes_call() -> None:
    report = CallReport(
        recording_id=RecordingId("rec-1"),
        satisfaction=Satisfaction.DISSATISFIED,
        summary="клиент жаловался на сроки",
        key_points=("жалоба", "сроки"),
        generated_at=datetime(2026, 1, 10, 12, 30, tzinfo=MSK),
    )
    assert report.satisfaction is Satisfaction.DISSATISFIED
    assert "сроки" in report.key_points
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/domain/test_report.py -v`
Expected: FAIL (ModuleNotFoundError: domain.report).

- [ ] **Step 3: Реализовать**

Create `src/domain/report.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from domain.recording import RecordingId


class Satisfaction(Enum):
    SATISFIED = auto()
    NEUTRAL = auto()
    DISSATISFIED = auto()


@dataclass(frozen=True, slots=True)
class CallReport:
    recording_id: RecordingId
    satisfaction: Satisfaction
    summary: str
    key_points: tuple[str, ...]
    generated_at: datetime


__all__ = ["CallReport", "Satisfaction"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/domain/test_report.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/domain/report.py tests/domain/test_report.py
git commit -m "feat(domain): call report model"
```

---

### Task 7: Домен — машина состояний job (errors.py + job.py)

**Files:**
- Create: `src/domain/errors.py`
- Create: `src/domain/job.py`
- Test: `tests/domain/test_job.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/domain/test_job.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from domain.errors import InvalidJobTransition
from domain.job import STAGE_ORDER, CallProcessingJob, JobStage, JobStatus
from domain.recording import RecordingId

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 1, 10, 12, 0, tzinfo=MSK)


def _job() -> CallProcessingJob:
    return CallProcessingJob.create("job-1", RecordingId("rec-1"), NOW)


def test_fresh_job_is_pending_at_first_stage() -> None:
    job = _job()
    assert job.status is JobStatus.PENDING
    assert job.next_stage() is JobStage.TRANSCRIBE
    assert job.completed_stages == frozenset()


def test_happy_path_runs_all_stages_to_done() -> None:
    job = _job()
    for stage in STAGE_ORDER:
        job = job.start_stage(stage)
        assert job.status is JobStatus.RUNNING
        job = job.complete_stage(stage)
    assert job.status is JobStatus.DONE
    assert job.next_stage() is None


def test_start_counts_attempts() -> None:
    job = _job().start_stage(JobStage.TRANSCRIBE)
    assert job.attempts[JobStage.TRANSCRIBE] == 1


def test_cannot_start_out_of_order_stage() -> None:
    job = _job()
    with pytest.raises(InvalidJobTransition):
        job.start_stage(JobStage.REPORT)


def test_cannot_complete_when_not_running() -> None:
    job = _job()
    with pytest.raises(InvalidJobTransition):
        job.complete_stage(JobStage.TRANSCRIBE)


def test_fail_then_retry_keeps_completed_and_reruns_failed_stage() -> None:
    job = _job()
    job = job.start_stage(JobStage.TRANSCRIBE).complete_stage(JobStage.TRANSCRIBE)
    job = job.start_stage(JobStage.DIARIZE).fail_stage(JobStage.DIARIZE, "TIMEOUT", "slow")
    assert job.status is JobStatus.FAILED
    assert job.last_error == ("TIMEOUT", "slow")

    job = job.retry()
    assert job.status is JobStatus.PENDING
    assert job.last_error is None
    assert JobStage.TRANSCRIBE in job.completed_stages
    assert job.next_stage() is JobStage.DIARIZE
    assert job.attempts[JobStage.TRANSCRIBE] == 1

    job = job.start_stage(JobStage.DIARIZE)
    assert job.attempts[JobStage.DIARIZE] == 2


def test_retry_only_from_failed() -> None:
    with pytest.raises(InvalidJobTransition):
        _job().retry()
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/domain/test_job.py -v`
Expected: FAIL (ModuleNotFoundError: domain.errors / domain.job).

- [ ] **Step 3: Реализовать**

Create `src/domain/errors.py`:

```python
from __future__ import annotations


class InvalidJobTransition(Exception):
    """Доменная ошибка: недопустимый переход машины состояний `CallProcessingJob`."""


__all__ = ["InvalidJobTransition"]
```

Create `src/domain/job.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from domain.errors import InvalidJobTransition
from domain.recording import RecordingId


class JobStage(Enum):
    TRANSCRIBE = "transcribe"
    DIARIZE = "diarize"
    EMOTION = "emotion"
    REPORT = "report"


STAGE_ORDER: tuple[JobStage, ...] = (
    JobStage.TRANSCRIBE,
    JobStage.DIARIZE,
    JobStage.EMOTION,
    JobStage.REPORT,
)


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CallProcessingJob:
    """Агрегат-машина состояний обработки одного звонка.

    Переходы возвращают новый экземпляр (иммутабельность). Стадии идут
    строго по `STAGE_ORDER`; нарушение порядка или статуса — это
    `InvalidJobTransition`. `next_stage()` всегда указывает на первую
    незавершённую стадию, поэтому повтор (`retry`) переигрывает именно
    упавшую стадию, не теряя уже посчитанные.
    """

    id: str
    recording_id: RecordingId
    status: JobStatus
    completed_stages: frozenset[JobStage]
    attempts: Mapping[JobStage, int]
    last_error: tuple[str, str] | None
    created_at: datetime

    @classmethod
    def create(
        cls, job_id: str, recording_id: RecordingId, now: datetime
    ) -> CallProcessingJob:
        return cls(
            id=job_id,
            recording_id=recording_id,
            status=JobStatus.PENDING,
            completed_stages=frozenset(),
            attempts={},
            last_error=None,
            created_at=now,
        )

    def next_stage(self) -> JobStage | None:
        for stage in STAGE_ORDER:
            if stage not in self.completed_stages:
                return stage
        return None

    def start_stage(self, stage: JobStage) -> CallProcessingJob:
        if self.status is not JobStatus.PENDING:
            raise InvalidJobTransition(
                f"нельзя начать стадию из статуса {self.status.name}"
            )
        if stage is not self.next_stage():
            raise InvalidJobTransition(f"стадия {stage.name} не является следующей")
        attempts = dict(self.attempts)
        attempts[stage] = attempts.get(stage, 0) + 1
        return replace(self, status=JobStatus.RUNNING, attempts=attempts)

    def complete_stage(self, stage: JobStage) -> CallProcessingJob:
        if self.status is not JobStatus.RUNNING:
            raise InvalidJobTransition(
                f"нельзя завершить стадию из статуса {self.status.name}"
            )
        if stage is not self.next_stage():
            raise InvalidJobTransition(f"завершается не текущая стадия {stage.name}")
        completed = self.completed_stages | {stage}
        done = all(s in completed for s in STAGE_ORDER)
        return replace(
            self,
            completed_stages=completed,
            status=JobStatus.DONE if done else JobStatus.PENDING,
            last_error=None,
        )

    def fail_stage(
        self, stage: JobStage, kind: str, message: str
    ) -> CallProcessingJob:
        if self.status is not JobStatus.RUNNING:
            raise InvalidJobTransition(
                f"нельзя пометить ошибку из статуса {self.status.name}"
            )
        return replace(self, status=JobStatus.FAILED, last_error=(kind, message))

    def retry(self) -> CallProcessingJob:
        if self.status is not JobStatus.FAILED:
            raise InvalidJobTransition(
                f"повтор возможен только из FAILED, текущий {self.status.name}"
            )
        return replace(self, status=JobStatus.PENDING, last_error=None)


__all__ = ["STAGE_ORDER", "CallProcessingJob", "JobStage", "JobStatus"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/domain/test_job.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/domain/errors.py src/domain/job.py tests/domain/test_job.py
git commit -m "feat(domain): call processing job state machine"
```

---

### Task 8: Граница домена — domain/__init__.py

**Files:**
- Modify: `src/domain/__init__.py`
- Test: `tests/domain/test_boundary.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/domain/test_boundary.py`:

```python
import domain


def test_domain_public_surface() -> None:
    expected = {
        "STAGE_ORDER",
        "AudioBlob",
        "CallProcessingJob",
        "CallRecording",
        "CallReport",
        "ChannelLayout",
        "DiarizedSegment",
        "DiarizedTranscript",
        "EmotionAnalysis",
        "EmotionLabel",
        "InvalidJobTransition",
        "JobStage",
        "JobStatus",
        "RecordingId",
        "Satisfaction",
        "SegmentEmotion",
        "SpeakerRole",
        "TimeSpan",
        "Transcript",
        "TranscriptSegment",
    }
    assert expected == set(domain.__all__)


def test_models_importable_from_boundary() -> None:
    from domain import CallProcessingJob, CallRecording, RecordingId

    assert CallRecording is not None
    assert CallProcessingJob is not None
    assert RecordingId is not None
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/domain/test_boundary.py -v`
Expected: FAIL (AttributeError: module 'domain' has no attribute '__all__' / ImportError).

- [ ] **Step 3: Реализовать**

Replace `src/domain/__init__.py` content with:

```python
from __future__ import annotations

from domain.diarization import DiarizedSegment, DiarizedTranscript, SpeakerRole
from domain.emotion import EmotionAnalysis, EmotionLabel, SegmentEmotion
from domain.errors import InvalidJobTransition
from domain.job import STAGE_ORDER, CallProcessingJob, JobStage, JobStatus
from domain.recording import AudioBlob, CallRecording, ChannelLayout, RecordingId
from domain.report import CallReport, Satisfaction
from domain.transcript import TimeSpan, Transcript, TranscriptSegment

__all__ = [
    "STAGE_ORDER",
    "AudioBlob",
    "CallProcessingJob",
    "CallRecording",
    "CallReport",
    "ChannelLayout",
    "DiarizedSegment",
    "DiarizedTranscript",
    "EmotionAnalysis",
    "EmotionLabel",
    "InvalidJobTransition",
    "JobStage",
    "JobStatus",
    "RecordingId",
    "Satisfaction",
    "SegmentEmotion",
    "SpeakerRole",
    "TimeSpan",
    "Transcript",
    "TranscriptSegment",
]
```

- [ ] **Step 4: Запустить — зелёный (весь домен)**

Run: `uv run pytest tests/domain/ -v`
Expected: PASS (все доменные тесты зелёные).

- [ ] **Step 5: Commit**

```bash
git add src/domain/__init__.py tests/domain/test_boundary.py
git commit -m "feat(domain): public boundary via __all__"
```

---

### Task 9: Порт CallRecordingSource

**Files:**
- Create: `src/call_analytics/__init__.py` (пустой)
- Create: `src/call_analytics/infra/__init__.py` (пустой)
- Create: `src/call_analytics/infra/ports/recording_source.py`
- Test: `tests/call_analytics/infra/ports/test_recording_source.py`

- [ ] **Step 1: Написать падающий тест**

Create пустые `__init__.py` в `tests/call_analytics/`, `tests/call_analytics/infra/`, `tests/call_analytics/infra/ports/`. Затем `tests/call_analytics/infra/ports/test_recording_source.py`:

```python
import pytest

from call_analytics.infra.ports.recording_source import (
    CallRecordingSource,
    CallRecordingSourceError,
)


def test_port_is_abstract() -> None:
    with pytest.raises(TypeError):
        CallRecordingSource()  # type: ignore[abstract]


def test_error_factory_sets_kind() -> None:
    err = CallRecordingSourceError.timeout("медленно")
    assert err.kind is CallRecordingSourceError.Kind.TIMEOUT
    assert "TIMEOUT" in str(err)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/call_analytics/infra/ports/test_recording_source.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Реализовать**

Create пустые `src/call_analytics/__init__.py` и `src/call_analytics/infra/__init__.py` (только `from __future__ import annotations`).

Create `src/call_analytics/infra/ports/recording_source.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from domain import AudioBlob, CallRecording, RecordingId


@dataclass(frozen=True, slots=True)
class Period:
    start: datetime
    end: datetime


class CallRecordingSourceError(Exception):
    """Контрактная ошибка `CallRecordingSource`.

    Адаптер источника записей (Naumen и т.п.) обязан заворачивать
    провайдер-специфичные исключения в этот класс. Вид — в `Kind`.
    """

    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        NOT_FOUND = auto()
        AUTH = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: CallRecordingSourceError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def not_found(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.NOT_FOUND, message)

    @classmethod
    def auth(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.AUTH, message)

    @classmethod
    def unexpected(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.UNEXPECTED, message)


class CallRecordingSource(ABC):
    """Абстрактный порт источника записей звонков (Naumen-экспорт)."""

    @abstractmethod
    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        """Список записей за период."""

    @abstractmethod
    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        """Скачать аудио записи по идентификатору."""


__all__ = ["CallRecordingSource", "CallRecordingSourceError", "Period"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/call_analytics/infra/ports/test_recording_source.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/call_analytics/__init__.py src/call_analytics/infra/__init__.py src/call_analytics/infra/ports/recording_source.py tests/call_analytics/
git commit -m "feat(infra): CallRecordingSource port"
```

---

### Task 10: Compute-порты (transcriber, diarizer, emotion_recognizer, report_generator)

**Files:**
- Create: `src/call_analytics/infra/ports/transcriber.py`
- Create: `src/call_analytics/infra/ports/diarizer.py`
- Create: `src/call_analytics/infra/ports/emotion_recognizer.py`
- Create: `src/call_analytics/infra/ports/report_generator.py`
- Test: `tests/call_analytics/infra/ports/test_compute_ports.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/call_analytics/infra/ports/test_compute_ports.py`:

```python
import pytest

from call_analytics.infra.ports.diarizer import SpeakerDiarizer, SpeakerDiarizerError
from call_analytics.infra.ports.emotion_recognizer import (
    EmotionRecognizer,
    EmotionRecognizerError,
)
from call_analytics.infra.ports.report_generator import (
    ReportGenerator,
    ReportGeneratorError,
)
from call_analytics.infra.ports.transcriber import Transcriber, TranscriberError


@pytest.mark.parametrize(
    "port",
    [Transcriber, SpeakerDiarizer, EmotionRecognizer, ReportGenerator],
)
def test_ports_are_abstract(port: type) -> None:
    with pytest.raises(TypeError):
        port()  # type: ignore[abstract]


def test_transcriber_error_kind() -> None:
    err = TranscriberError.invalid_format("не wav")
    assert err.kind is TranscriberError.Kind.INVALID_FORMAT


def test_diarizer_error_kind() -> None:
    err = SpeakerDiarizerError.unexpected("ой")
    assert err.kind is SpeakerDiarizerError.Kind.UNEXPECTED


def test_emotion_error_kind() -> None:
    err = EmotionRecognizerError.timeout("долго")
    assert err.kind is EmotionRecognizerError.Kind.TIMEOUT


def test_report_error_kind() -> None:
    err = ReportGeneratorError.rate_limit("429")
    assert err.kind is ReportGeneratorError.Kind.RATE_LIMIT
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/call_analytics/infra/ports/test_compute_ports.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Реализовать**

Create `src/call_analytics/infra/ports/transcriber.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto

from domain import AudioBlob, Transcript


class TranscriberError(Exception):
    """Контрактная ошибка `Transcriber` (faster-whisper и т.п.)."""

    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        INVALID_FORMAT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: TranscriberError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> TranscriberError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> TranscriberError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def invalid_format(cls, message: str) -> TranscriberError:
        return cls(cls.Kind.INVALID_FORMAT, message)

    @classmethod
    def unexpected(cls, message: str) -> TranscriberError:
        return cls(cls.Kind.UNEXPECTED, message)


class Transcriber(ABC):
    """Абстрактный порт распознавания речи в текст."""

    @abstractmethod
    async def transcribe(self, audio: AudioBlob) -> Transcript:
        """Распознать аудио в `Transcript` с тайм-кодами по сегментам."""


__all__ = ["Transcriber", "TranscriberError"]
```

Create `src/call_analytics/infra/ports/diarizer.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto

from domain import AudioBlob, DiarizedTranscript, Transcript


class SpeakerDiarizerError(Exception):
    """Контрактная ошибка `SpeakerDiarizer`.

    Реализация сама решает стратегию: разбивка по стерео-каналам
    (оператор=0/клиент=1) либо ML-диаризация для моно. Сервис разницы
    не видит.
    """

    class Kind(Enum):
        INVALID_FORMAT = auto()
        TIMEOUT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: SpeakerDiarizerError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def invalid_format(cls, message: str) -> SpeakerDiarizerError:
        return cls(cls.Kind.INVALID_FORMAT, message)

    @classmethod
    def timeout(cls, message: str) -> SpeakerDiarizerError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def unexpected(cls, message: str) -> SpeakerDiarizerError:
        return cls(cls.Kind.UNEXPECTED, message)


class SpeakerDiarizer(ABC):
    """Абстрактный порт разметки говорящих (оператор/клиент)."""

    @abstractmethod
    async def diarize(
        self, audio: AudioBlob, transcript: Transcript
    ) -> DiarizedTranscript:
        """Привязать сегменты транскрипта к ролям говорящих."""


__all__ = ["SpeakerDiarizer", "SpeakerDiarizerError"]
```

Create `src/call_analytics/infra/ports/emotion_recognizer.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto

from domain import AudioBlob, DiarizedTranscript, EmotionAnalysis


class EmotionRecognizerError(Exception):
    """Контрактная ошибка `EmotionRecognizer` (SER-модель)."""

    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        INVALID_FORMAT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: EmotionRecognizerError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> EmotionRecognizerError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> EmotionRecognizerError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def invalid_format(cls, message: str) -> EmotionRecognizerError:
        return cls(cls.Kind.INVALID_FORMAT, message)

    @classmethod
    def unexpected(cls, message: str) -> EmotionRecognizerError:
        return cls(cls.Kind.UNEXPECTED, message)


class EmotionRecognizer(ABC):
    """Абстрактный порт распознавания эмоций по сегментам речи."""

    @abstractmethod
    async def recognize(
        self, audio: AudioBlob, diarized: DiarizedTranscript
    ) -> EmotionAnalysis:
        """Определить эмоции для сегментов размеченного транскрипта."""


__all__ = ["EmotionRecognizer", "EmotionRecognizerError"]
```

Create `src/call_analytics/infra/ports/report_generator.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto

from domain import CallReport, DiarizedTranscript, EmotionAnalysis


class ReportGeneratorError(Exception):
    """Контрактная ошибка `ReportGenerator` (qwen и т.п.)."""

    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        RATE_LIMIT = auto()
        INVALID_REQUEST = auto()
        SERVER = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: ReportGeneratorError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def rate_limit(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.RATE_LIMIT, message)

    @classmethod
    def invalid_request(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.INVALID_REQUEST, message)

    @classmethod
    def server(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.SERVER, message)

    @classmethod
    def unexpected(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.UNEXPECTED, message)


class ReportGenerator(ABC):
    """Абстрактный порт генерации отчёта об удовлетворённости и содержании."""

    @abstractmethod
    async def generate(
        self, diarized: DiarizedTranscript, emotions: EmotionAnalysis
    ) -> CallReport:
        """Построить `CallReport` по размеченному транскрипту и эмоциям."""


__all__ = ["ReportGenerator", "ReportGeneratorError"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/call_analytics/infra/ports/test_compute_ports.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/call_analytics/infra/ports/transcriber.py src/call_analytics/infra/ports/diarizer.py src/call_analytics/infra/ports/emotion_recognizer.py src/call_analytics/infra/ports/report_generator.py tests/call_analytics/infra/ports/test_compute_ports.py
git commit -m "feat(infra): transcriber/diarizer/emotion/report ports"
```

---

### Task 11: Порты персистенции (JobRepository, ArtifactStore)

**Files:**
- Create: `src/call_analytics/infra/ports/job_repository.py`
- Create: `src/call_analytics/infra/ports/artifact_store.py`
- Test: `tests/call_analytics/infra/ports/test_persistence_ports.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/call_analytics/infra/ports/test_persistence_ports.py`:

```python
import pytest

from call_analytics.infra.ports.artifact_store import ArtifactStore
from call_analytics.infra.ports.job_repository import JobRepository


@pytest.mark.parametrize("port", [JobRepository, ArtifactStore])
def test_persistence_ports_are_abstract(port: type) -> None:
    with pytest.raises(TypeError):
        port()  # type: ignore[abstract]
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/call_analytics/infra/ports/test_persistence_ports.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Реализовать**

Create `src/call_analytics/infra/ports/job_repository.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from domain import CallProcessingJob, JobStatus


class JobRepository(ABC):
    """Абстрактный порт персистенции машины состояний job."""

    @abstractmethod
    async def save(self, job: CallProcessingJob) -> None:
        """Сохранить (upsert) состояние job."""

    @abstractmethod
    async def get(self, job_id: str) -> CallProcessingJob | None:
        """Прочитать job по идентификатору или `None`."""

    @abstractmethod
    async def list_by_status(self, status: JobStatus) -> Sequence[CallProcessingJob]:
        """Список job в указанном статусе."""


__all__ = ["JobRepository"]
```

Create `src/call_analytics/infra/ports/artifact_store.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from domain import (
    CallRecording,
    CallReport,
    DiarizedTranscript,
    EmotionAnalysis,
    RecordingId,
    Transcript,
)


class ArtifactStore(ABC):
    """Абстрактный порт хранения выходов стадий пайплайна.

    Персист промежуточных артефактов делает ретрай идемпотентным:
    упавшая поздняя стадия не пересчитывает дорогой whisper.
    """

    @abstractmethod
    async def save_recording(self, recording: CallRecording) -> None: ...

    @abstractmethod
    async def load_recording(self, recording_id: RecordingId) -> CallRecording | None: ...

    @abstractmethod
    async def save_transcript(self, transcript: Transcript) -> None: ...

    @abstractmethod
    async def load_transcript(self, recording_id: RecordingId) -> Transcript | None: ...

    @abstractmethod
    async def save_diarization(self, diarized: DiarizedTranscript) -> None: ...

    @abstractmethod
    async def load_diarization(
        self, recording_id: RecordingId
    ) -> DiarizedTranscript | None: ...

    @abstractmethod
    async def save_emotion(self, emotion: EmotionAnalysis) -> None: ...

    @abstractmethod
    async def load_emotion(self, recording_id: RecordingId) -> EmotionAnalysis | None: ...

    @abstractmethod
    async def save_report(self, report: CallReport) -> None: ...

    @abstractmethod
    async def load_report(self, recording_id: RecordingId) -> CallReport | None: ...


__all__ = ["ArtifactStore"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/call_analytics/infra/ports/test_persistence_ports.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/call_analytics/infra/ports/job_repository.py src/call_analytics/infra/ports/artifact_store.py tests/call_analytics/infra/ports/test_persistence_ports.py
git commit -m "feat(infra): JobRepository and ArtifactStore ports"
```

---

### Task 12: Граница портов — infra/ports/__init__.py

**Files:**
- Create: `src/call_analytics/infra/ports/__init__.py`
- Test: `tests/call_analytics/infra/ports/test_ports_boundary.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/call_analytics/infra/ports/test_ports_boundary.py`:

```python
from call_analytics.infra import ports


def test_ports_boundary_exports() -> None:
    expected = {
        "ArtifactStore",
        "CallRecordingSource",
        "CallRecordingSourceError",
        "EmotionRecognizer",
        "EmotionRecognizerError",
        "JobRepository",
        "Period",
        "ReportGenerator",
        "ReportGeneratorError",
        "SpeakerDiarizer",
        "SpeakerDiarizerError",
        "Transcriber",
        "TranscriberError",
    }
    assert expected == set(ports.__all__)


def test_imports_from_boundary() -> None:
    from call_analytics.infra.ports import CallRecordingSource, Transcriber

    assert CallRecordingSource is not None
    assert Transcriber is not None
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/call_analytics/infra/ports/test_ports_boundary.py -v`
Expected: FAIL (AttributeError: __all__ / ImportError).

- [ ] **Step 3: Реализовать**

Create `src/call_analytics/infra/ports/__init__.py`:

```python
from __future__ import annotations

from call_analytics.infra.ports.artifact_store import ArtifactStore
from call_analytics.infra.ports.diarizer import SpeakerDiarizer, SpeakerDiarizerError
from call_analytics.infra.ports.emotion_recognizer import (
    EmotionRecognizer,
    EmotionRecognizerError,
)
from call_analytics.infra.ports.job_repository import JobRepository
from call_analytics.infra.ports.recording_source import (
    CallRecordingSource,
    CallRecordingSourceError,
    Period,
)
from call_analytics.infra.ports.report_generator import (
    ReportGenerator,
    ReportGeneratorError,
)
from call_analytics.infra.ports.transcriber import Transcriber, TranscriberError

__all__ = [
    "ArtifactStore",
    "CallRecordingSource",
    "CallRecordingSourceError",
    "EmotionRecognizer",
    "EmotionRecognizerError",
    "JobRepository",
    "Period",
    "ReportGenerator",
    "ReportGeneratorError",
    "SpeakerDiarizer",
    "SpeakerDiarizerError",
    "Transcriber",
    "TranscriberError",
]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/call_analytics/infra/ports/test_ports_boundary.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/call_analytics/infra/ports/__init__.py tests/call_analytics/infra/ports/test_ports_boundary.py
git commit -m "feat(infra): ports package boundary"
```

---

### Task 13: noop-адаптеры compute-портов

**Files:**
- Create: `src/call_analytics/infra/adapters/__init__.py` (пустой)
- Create: `src/call_analytics/infra/adapters/noop/__init__.py`
- Create: `src/call_analytics/infra/adapters/noop/adapters.py`
- Test: `tests/call_analytics/infra/adapters/test_noop.py`

- [ ] **Step 1: Написать падающий тест**

Create `__init__.py` в `tests/call_analytics/infra/adapters/` (empty), затем `tests/call_analytics/infra/adapters/test_noop.py`:

```python
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
    tr = await NoopTranscriber(RID).transcribe(blob)
    assert isinstance(tr, Transcript)
    assert tr.recording_id == RID
    assert tr.segments


async def test_noop_diarizer_maps_channel_to_role() -> None:
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(
            TranscriptSegment(TimeSpan(timedelta(0), timedelta(seconds=1)), "оператор", channel=0),
            TranscriptSegment(TimeSpan(timedelta(seconds=1), timedelta(seconds=2)), "клиент", channel=1),
            TranscriptSegment(TimeSpan(timedelta(seconds=2), timedelta(seconds=3)), "?", channel=None),
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
    dt = DiarizedTranscript(recording_id=RID, segments=())
    ea = EmotionAnalysis(recording_id=RID, segments=())
    generated_at = datetime(2026, 1, 10, tzinfo=MSK)
    report = await NoopReportGenerator(generated_at=generated_at).generate(dt, ea)
    assert report.recording_id == RID
    assert report.summary
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/call_analytics/infra/adapters/test_noop.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Реализовать**

Create `src/call_analytics/infra/adapters/__init__.py` (только `from __future__ import annotations`).

Create `src/call_analytics/infra/adapters/noop/adapters.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta

from call_analytics.infra.ports import (
    EmotionRecognizer,
    ReportGenerator,
    SpeakerDiarizer,
    Transcriber,
)
from domain import (
    AudioBlob,
    CallReport,
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
)

_CHANNEL_ROLE = {0: SpeakerRole.OPERATOR, 1: SpeakerRole.CLIENT}


class NoopTranscriber(Transcriber):
    """Детерминированная заглушка распознавания для тестов."""

    def __init__(self, recording_id: RecordingId) -> None:
        self._recording_id = recording_id

    async def transcribe(self, audio: AudioBlob) -> Transcript:
        segment = TranscriptSegment(
            span=TimeSpan(start=timedelta(0), end=timedelta(seconds=1)),
            text="noop",
            channel=0,
            confidence=1.0,
        )
        return Transcript(
            recording_id=self._recording_id,
            language="ru",
            segments=(segment,),
            full_text="noop",
        )


class NoopDiarizer(SpeakerDiarizer):
    """Заглушка: роль по номеру стерео-канала, иначе UNKNOWN."""

    async def diarize(
        self, audio: AudioBlob, transcript: Transcript
    ) -> DiarizedTranscript:
        segments = tuple(
            DiarizedSegment(
                span=seg.span,
                role=_CHANNEL_ROLE.get(seg.channel, SpeakerRole.UNKNOWN)
                if seg.channel is not None
                else SpeakerRole.UNKNOWN,
                text=seg.text,
            )
            for seg in transcript.segments
        )
        return DiarizedTranscript(
            recording_id=transcript.recording_id, segments=segments
        )


class NoopEmotionRecognizer(EmotionRecognizer):
    """Заглушка: всем сегментам NEUTRAL."""

    async def recognize(
        self, audio: AudioBlob, diarized: DiarizedTranscript
    ) -> EmotionAnalysis:
        segments = tuple(
            SegmentEmotion(
                span=seg.span,
                role=seg.role,
                label=EmotionLabel.NEUTRAL,
                scores={EmotionLabel.NEUTRAL: 1.0},
            )
            for seg in diarized.segments
        )
        return EmotionAnalysis(
            recording_id=diarized.recording_id, segments=segments
        )


class NoopReportGenerator(ReportGenerator):
    """Заглушка отчёта с фиксированным таймстампом."""

    def __init__(self, generated_at: datetime) -> None:
        self._generated_at = generated_at

    async def generate(
        self, diarized: DiarizedTranscript, emotions: EmotionAnalysis
    ) -> CallReport:
        return CallReport(
            recording_id=diarized.recording_id,
            satisfaction=Satisfaction.NEUTRAL,
            summary="noop summary",
            key_points=(),
            generated_at=self._generated_at,
        )


__all__ = [
    "NoopDiarizer",
    "NoopEmotionRecognizer",
    "NoopReportGenerator",
    "NoopTranscriber",
]
```

Create `src/call_analytics/infra/adapters/noop/__init__.py`:

```python
from __future__ import annotations

from call_analytics.infra.adapters.noop.adapters import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)

__all__ = [
    "NoopDiarizer",
    "NoopEmotionRecognizer",
    "NoopReportGenerator",
    "NoopTranscriber",
]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/call_analytics/infra/adapters/test_noop.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/call_analytics/infra/adapters/__init__.py src/call_analytics/infra/adapters/noop/ tests/call_analytics/infra/adapters/
git commit -m "feat(adapters): noop compute adapters"
```

---

### Task 14: in_memory-адаптеры персистенции

**Files:**
- Create: `src/call_analytics/infra/adapters/in_memory/__init__.py`
- Create: `src/call_analytics/infra/adapters/in_memory/repositories.py`
- Test: `tests/call_analytics/infra/adapters/test_in_memory.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/call_analytics/infra/adapters/test_in_memory.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
)
from domain import (
    CallProcessingJob,
    DiarizedTranscript,
    JobStatus,
    RecordingId,
    Transcript,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
RID = RecordingId("rec-1")


async def test_job_repository_roundtrip_and_query() -> None:
    repo = InMemoryJobRepository()
    job = CallProcessingJob.create("job-1", RID, datetime(2026, 1, 10, tzinfo=MSK))
    await repo.save(job)
    assert await repo.get("job-1") == job
    assert await repo.get("missing") is None
    pending = await repo.list_by_status(JobStatus.PENDING)
    assert list(pending) == [job]
    assert list(await repo.list_by_status(JobStatus.DONE)) == []


async def test_artifact_store_roundtrip() -> None:
    store = InMemoryArtifactStore()
    transcript = Transcript(recording_id=RID, language="ru", segments=(), full_text="")
    await store.save_transcript(transcript)
    assert await store.load_transcript(RID) == transcript
    assert await store.load_diarization(RID) is None
    diar = DiarizedTranscript(recording_id=RID, segments=())
    await store.save_diarization(diar)
    assert await store.load_diarization(RID) == diar
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/call_analytics/infra/adapters/test_in_memory.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Реализовать**

Create `src/call_analytics/infra/adapters/in_memory/repositories.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from call_analytics.infra.ports import ArtifactStore, JobRepository
from domain import (
    CallProcessingJob,
    CallRecording,
    CallReport,
    DiarizedTranscript,
    EmotionAnalysis,
    JobStatus,
    RecordingId,
    Transcript,
)


class InMemoryJobRepository(JobRepository):
    """Словарная реализация `JobRepository` для тестов."""

    def __init__(self) -> None:
        self._jobs: dict[str, CallProcessingJob] = {}

    async def save(self, job: CallProcessingJob) -> None:
        self._jobs[job.id] = job

    async def get(self, job_id: str) -> CallProcessingJob | None:
        return self._jobs.get(job_id)

    async def list_by_status(
        self, status: JobStatus
    ) -> Sequence[CallProcessingJob]:
        return [job for job in self._jobs.values() if job.status is status]


class InMemoryArtifactStore(ArtifactStore):
    """Словарная реализация `ArtifactStore` для тестов."""

    def __init__(self) -> None:
        self._recordings: dict[str, CallRecording] = {}
        self._transcripts: dict[str, Transcript] = {}
        self._diarizations: dict[str, DiarizedTranscript] = {}
        self._emotions: dict[str, EmotionAnalysis] = {}
        self._reports: dict[str, CallReport] = {}

    async def save_recording(self, recording: CallRecording) -> None:
        self._recordings[recording.id.value] = recording

    async def load_recording(
        self, recording_id: RecordingId
    ) -> CallRecording | None:
        return self._recordings.get(recording_id.value)

    async def save_transcript(self, transcript: Transcript) -> None:
        self._transcripts[transcript.recording_id.value] = transcript

    async def load_transcript(
        self, recording_id: RecordingId
    ) -> Transcript | None:
        return self._transcripts.get(recording_id.value)

    async def save_diarization(self, diarized: DiarizedTranscript) -> None:
        self._diarizations[diarized.recording_id.value] = diarized

    async def load_diarization(
        self, recording_id: RecordingId
    ) -> DiarizedTranscript | None:
        return self._diarizations.get(recording_id.value)

    async def save_emotion(self, emotion: EmotionAnalysis) -> None:
        self._emotions[emotion.recording_id.value] = emotion

    async def load_emotion(
        self, recording_id: RecordingId
    ) -> EmotionAnalysis | None:
        return self._emotions.get(recording_id.value)

    async def save_report(self, report: CallReport) -> None:
        self._reports[report.recording_id.value] = report

    async def load_report(self, recording_id: RecordingId) -> CallReport | None:
        return self._reports.get(recording_id.value)


__all__ = ["InMemoryArtifactStore", "InMemoryJobRepository"]
```

Create `src/call_analytics/infra/adapters/in_memory/__init__.py`:

```python
from __future__ import annotations

from call_analytics.infra.adapters.in_memory.repositories import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
)

__all__ = ["InMemoryArtifactStore", "InMemoryJobRepository"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/call_analytics/infra/adapters/test_in_memory.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/call_analytics/infra/adapters/in_memory/ tests/call_analytics/infra/adapters/test_in_memory.py
git commit -m "feat(adapters): in-memory job repository and artifact store"
```

---

### Task 15: Интерфейс use-case (service/ports/pipeline.py)

**Files:**
- Create: `src/call_analytics/service/__init__.py` (пустой пока)
- Create: `src/call_analytics/service/ports/__init__.py`
- Create: `src/call_analytics/service/ports/pipeline.py`
- Test: `tests/call_analytics/service/test_pipeline_port.py`

- [ ] **Step 1: Написать падающий тест**

Create `__init__.py` в `tests/call_analytics/service/` (empty), затем `tests/call_analytics/service/test_pipeline_port.py`:

```python
import pytest

from call_analytics.service.ports import CallProcessingPipeline


def test_pipeline_port_is_abstract() -> None:
    with pytest.raises(TypeError):
        CallProcessingPipeline()  # type: ignore[abstract]
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/call_analytics/service/test_pipeline_port.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Реализовать**

Create `src/call_analytics/service/__init__.py` (только `from __future__ import annotations`).

Create `src/call_analytics/service/ports/pipeline.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from domain import CallProcessingJob, CallRecording, RecordingId


class CallProcessingPipeline(ABC):
    """Интерфейс use-case обработки звонка по стадиям."""

    @abstractmethod
    async def enqueue(self, recording: CallRecording) -> CallProcessingJob:
        """Поставить запись в обработку, создать job в PENDING."""

    @abstractmethod
    async def run_next_stage(self, job_id: str) -> CallProcessingJob:
        """Выполнить следующую незавершённую стадию job."""

    @abstractmethod
    async def process(self, recording_id: RecordingId) -> CallProcessingJob:
        """Прогнать пайплайн до завершения или первой ошибки."""

    @abstractmethod
    async def retry(self, job_id: str) -> CallProcessingJob:
        """Сбросить упавшую стадию в PENDING для повтора."""


__all__ = ["CallProcessingPipeline"]
```

Create `src/call_analytics/service/ports/__init__.py`:

```python
from __future__ import annotations

from call_analytics.service.ports.pipeline import CallProcessingPipeline

__all__ = ["CallProcessingPipeline"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/call_analytics/service/test_pipeline_port.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/call_analytics/service/__init__.py src/call_analytics/service/ports/ tests/call_analytics/service/
git commit -m "feat(service): CallProcessingPipeline use-case interface"
```

---

### Task 16: Сервис-оркестратор (service/pipeline.py)

**Files:**
- Create: `src/call_analytics/service/pipeline.py`
- Modify: `src/call_analytics/service/__init__.py`
- Test: `tests/call_analytics/service/conftest.py`
- Test: `tests/call_analytics/service/test_call_processing_service.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/call_analytics/service/conftest.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from call_analytics.infra.ports import CallRecordingSource, Period
from domain import AudioBlob, CallRecording, ChannelLayout, RecordingId


class FakeRecordingSource(CallRecordingSource):
    """Фейковый источник: отдаёт заранее положенное аудио."""

    def __init__(self, audio: dict[str, AudioBlob]) -> None:
        self._audio = audio

    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        return []

    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        return self._audio[recording_id.value]


class FailingTranscriber:
    """Транскрайбер, бросающий контрактную ошибку при первом вызове."""

    def __init__(self, error: Exception, then: object) -> None:
        self._error = error
        self._then = then
        self.calls = 0

    async def transcribe(self, audio: AudioBlob):  # noqa: ANN201
        self.calls += 1
        if self.calls == 1:
            raise self._error
        return await self._then.transcribe(audio)


def stereo_blob() -> AudioBlob:
    return AudioBlob(data=b"x", codec="wav/gsm0610", layout=ChannelLayout.STEREO)
```

Create `tests/call_analytics/service/test_call_processing_service.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
)
from call_analytics.infra.adapters.noop import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)
from call_analytics.infra.ports import TranscriberError
from call_analytics.service.pipeline import CallProcessingService
from domain import CallRecording, ChannelLayout, JobStatus, RecordingId

from tests.call_analytics.service.conftest import (
    FailingTranscriber,
    FakeRecordingSource,
    stereo_blob,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 1, 10, 12, 0, tzinfo=MSK)
RID = RecordingId("rec-1")


def _recording() -> CallRecording:
    return CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=5),
        channel_layout=ChannelLayout.STEREO,
    )


def _service(jobs, artifacts, transcriber=None):
    return CallProcessingService(
        source=FakeRecordingSource({RID.value: stereo_blob()}),
        transcriber=transcriber or NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: NOW,
    )


async def test_process_runs_pipeline_to_done_and_writes_report() -> None:
    jobs, artifacts = InMemoryJobRepository(), InMemoryArtifactStore()
    service = _service(jobs, artifacts)

    await service.enqueue(_recording())
    job = await service.process(RID)

    assert job.status is JobStatus.DONE
    assert await artifacts.load_transcript(RID) is not None
    assert await artifacts.load_diarization(RID) is not None
    assert await artifacts.load_emotion(RID) is not None
    assert await artifacts.load_report(RID) is not None


async def test_run_next_stage_is_idempotent_for_completed_stage() -> None:
    jobs, artifacts = InMemoryJobRepository(), InMemoryArtifactStore()
    service = _service(jobs, artifacts)
    job = await service.enqueue(_recording())

    job = await service.run_next_stage(job.id)
    assert job.status is JobStatus.PENDING
    transcript = await artifacts.load_transcript(RID)

    job = await service.run_next_stage(job.id)
    assert await artifacts.load_transcript(RID) == transcript


async def test_failed_stage_then_retry_recomputes_only_failed_stage() -> None:
    jobs, artifacts = InMemoryJobRepository(), InMemoryArtifactStore()
    failing = FailingTranscriber(
        error=TranscriberError.timeout("медленно"), then=NoopTranscriber(RID)
    )
    service = _service(jobs, artifacts, transcriber=failing)
    await service.enqueue(_recording())

    job = await service.process(RID)
    assert job.status is JobStatus.FAILED
    assert job.last_error is not None and job.last_error[0] == "TIMEOUT"
    assert await artifacts.load_transcript(RID) is None

    job = await service.retry(job.id)
    job = await service.process(RID)
    assert job.status is JobStatus.DONE
    assert failing.calls == 2
    assert await artifacts.load_report(RID) is not None
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/call_analytics/service/test_call_processing_service.py -v`
Expected: FAIL (ModuleNotFoundError: call_analytics.service.pipeline).

- [ ] **Step 3: Реализовать**

Create `src/call_analytics/service/pipeline.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from call_analytics.infra.ports import (
    ArtifactStore,
    CallRecordingSource,
    CallRecordingSourceError,
    EmotionRecognizer,
    EmotionRecognizerError,
    JobRepository,
    ReportGenerator,
    ReportGeneratorError,
    SpeakerDiarizer,
    SpeakerDiarizerError,
    Transcriber,
    TranscriberError,
)
from call_analytics.service.ports import CallProcessingPipeline
from domain import (
    AudioBlob,
    CallProcessingJob,
    CallRecording,
    JobStage,
    JobStatus,
    RecordingId,
)

_PORT_ERRORS = (
    CallRecordingSourceError,
    TranscriberError,
    SpeakerDiarizerError,
    EmotionRecognizerError,
    ReportGeneratorError,
)


class CallProcessingService(CallProcessingPipeline):
    """Оркестратор пайплайна поверх инфра-портов.

    Зависит только от портов и домена. Каждая стадия читает вход из
    `ArtifactStore` (или скачивает аудио), вызывает compute-порт,
    сохраняет выход и двигает доменный агрегат `CallProcessingJob`.
    Ошибка порта переводит job в FAILED с сохранёнными артефактами
    предыдущих стадий — повтор переигрывает только упавшую стадию.
    """

    def __init__(
        self,
        source: CallRecordingSource,
        transcriber: Transcriber,
        diarizer: SpeakerDiarizer,
        emotion_recognizer: EmotionRecognizer,
        report_generator: ReportGenerator,
        jobs: JobRepository,
        artifacts: ArtifactStore,
        clock: Callable[[], datetime],
    ) -> None:
        self._source = source
        self._transcriber = transcriber
        self._diarizer = diarizer
        self._emotion_recognizer = emotion_recognizer
        self._report_generator = report_generator
        self._jobs = jobs
        self._artifacts = artifacts
        self._clock = clock

    async def enqueue(self, recording: CallRecording) -> CallProcessingJob:
        job = CallProcessingJob.create(
            job_id=recording.id.value,
            recording_id=recording.id,
            now=self._clock(),
        )
        await self._artifacts.save_recording(recording)
        await self._jobs.save(job)
        return job

    async def run_next_stage(self, job_id: str) -> CallProcessingJob:
        job = await self._require_job(job_id)
        stage = job.next_stage()
        if stage is None or job.status is not JobStatus.PENDING:
            return job

        job = job.start_stage(stage)
        await self._jobs.save(job)
        try:
            await self._execute(stage, job.recording_id)
        except _PORT_ERRORS as error:
            job = job.fail_stage(stage, error.kind.name, str(error))
            await self._jobs.save(job)
            return job

        job = job.complete_stage(stage)
        await self._jobs.save(job)
        return job

    async def process(self, recording_id: RecordingId) -> CallProcessingJob:
        job = await self._require_job(recording_id.value)
        while job.status is JobStatus.PENDING and job.next_stage() is not None:
            job = await self.run_next_stage(job.id)
            if job.status is JobStatus.FAILED:
                break
        return job

    async def retry(self, job_id: str) -> CallProcessingJob:
        job = await self._require_job(job_id)
        job = job.retry()
        await self._jobs.save(job)
        return job

    async def _execute(self, stage: JobStage, recording_id: RecordingId) -> None:
        if stage is JobStage.TRANSCRIBE:
            audio = await self._fetch_audio(recording_id)
            transcript = await self._transcriber.transcribe(audio)
            await self._artifacts.save_transcript(transcript)
        elif stage is JobStage.DIARIZE:
            audio = await self._fetch_audio(recording_id)
            transcript = await self._artifacts.load_transcript(recording_id)
            assert transcript is not None
            diarized = await self._diarizer.diarize(audio, transcript)
            await self._artifacts.save_diarization(diarized)
        elif stage is JobStage.EMOTION:
            audio = await self._fetch_audio(recording_id)
            diarized = await self._artifacts.load_diarization(recording_id)
            assert diarized is not None
            emotion = await self._emotion_recognizer.recognize(audio, diarized)
            await self._artifacts.save_emotion(emotion)
        elif stage is JobStage.REPORT:
            diarized = await self._artifacts.load_diarization(recording_id)
            emotion = await self._artifacts.load_emotion(recording_id)
            assert diarized is not None and emotion is not None
            report = await self._report_generator.generate(diarized, emotion)
            await self._artifacts.save_report(report)

    async def _fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        return await self._source.fetch_audio(recording_id)

    async def _require_job(self, job_id: str) -> CallProcessingJob:
        job = await self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"job {job_id} не найден")
        return job


__all__ = ["CallProcessingService"]
```

Replace `src/call_analytics/service/__init__.py` content with:

```python
from __future__ import annotations

from call_analytics.service.pipeline import CallProcessingService

__all__ = ["CallProcessingService"]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/call_analytics/service/test_call_processing_service.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/call_analytics/service/pipeline.py src/call_analytics/service/__init__.py tests/call_analytics/service/
git commit -m "feat(service): CallProcessingService stage orchestrator"
```

---

### Task 17: Полный прогон, линтеры, типы

**Files:** (без новых)

- [ ] **Step 1: Прогнать весь тест-сьют**

Run: `uv run pytest -v`
Expected: PASS (все тесты зелёные).

- [ ] **Step 2: ruff**

Run: `uv run ruff check src tests`
Expected: All checks passed. (Если есть замечания — исправить, не меняя поведение.)

- [ ] **Step 3: mypy**

Run: `uv run mypy src`
Expected: Success: no issues found. (Если strict ругается на `assert ... is not None` — оставить, это сужение типа; реальные ошибки типов исправить.)

- [ ] **Step 4: Финальный коммит**

```bash
git add -A
git commit -m "chore: green test suite, lint and types clean"
```

---

## Self-Review (выполнено при написании плана)

**1. Покрытие спеки:**
- Раскладка пакетов + границы `__all__` → Tasks 1, 8, 12, 15, 16 (и `__init__` в каждом).
- Доменная модель (recording/transcript/diarization/emotion/report) → Tasks 2–6.
- Машина состояний job → Task 7.
- 7 инфра-портов → Tasks 9, 10, 11.
- Единый `SpeakerDiarizer` (mono/stereo решает адаптер) → Task 10 (порт) + Task 13 (noop по каналам).
- Сервис-оркестратор + идемпотентность + ретрай только упавшей стадии → Task 16.
- Обработка ошибок (`<Port>Error.Kind`, `InvalidJobTransition`) → Tasks 7, 9, 10, 16.
- Тестовая стратегия (noop/in_memory фейки, полный прогон, идемпотентность, ретрай) → Tasks 13, 14, 16.

**2. Placeholder-скан:** TODO/TBD/«добавить обработку ошибок» — нет; код приведён полностью в каждом шаге.

**3. Согласованность типов:** имена методов портов (`transcribe`, `diarize`, `recognize`, `generate`, `save_*`/`load_*`, `save`/`get`/`list_by_status`), сигнатуры машины состояний (`start_stage`/`complete_stage`/`fail_stage`/`retry`/`next_stage`) и `error.kind.name` совпадают между задачами определения и использования (Task 16 ловит `_PORT_ERRORS` из границы `call_analytics.infra.ports`, у всех есть `.kind`).

**4. Вне объёма (YAGNI):** реальные адаптеры Naumen/whisper/SER/qwen, планировщик/очередь, БД-схемы, web-API — отдельный цикл (раздел 9 спеки).
