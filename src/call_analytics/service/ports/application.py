from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import Enum, auto
from typing import NamedTuple, Protocol

from domain import (
    AudioBlob,
    CallProcessingJob,
    CallRecording,
    CallReport,
    DiarizedTranscript,
    EmotionAnalysis,
    JobStatus,
    Period,
    RecordingId,
    SynchronizedDialogue,
    Transcript,
)


class CallRecordingSourceError(Exception):
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
    @abstractmethod
    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        """Список записей за период."""

    @abstractmethod
    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        """Скачать аудио записи по идентификатору."""


class TranscriberError(Exception):
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
    @abstractmethod
    async def transcribe(self, recording_id: RecordingId, audio: AudioBlob) -> Transcript:
        """Распознать аудио в `Transcript` с тайм-кодами по сегментам."""


class SpeakerDiarizerError(Exception):
    class Kind(Enum):
        CONNECTION = auto()
        INVALID_FORMAT = auto()
        TIMEOUT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: SpeakerDiarizerError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> SpeakerDiarizerError:
        return cls(cls.Kind.CONNECTION, message)

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
    @abstractmethod
    async def diarize(self, audio: AudioBlob, transcript: Transcript) -> DiarizedTranscript:
        """Привязать сегменты транскрипта к ролям говорящих."""


class EmotionRecognizerError(Exception):
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
    @abstractmethod
    async def recognize(self, audio: AudioBlob, diarized: DiarizedTranscript) -> EmotionAnalysis:
        """Определить эмоции для сегментов размеченного транскрипта."""


class ReportGeneratorError(Exception):
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
    @abstractmethod
    async def generate(
        self,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> CallReport:
        """Построить `CallReport` по размеченному транскрипту и эмоциям."""


class ReportRenderer(ABC):
    @abstractmethod
    async def render(
        self,
        report: CallReport,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> bytes:
        """Render the final human-readable report artifact."""


class ReportRendererError(Exception):
    class Kind(Enum):
        UNEXPECTED = auto()

    def __init__(self, kind: ReportRendererError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def unexpected(cls, message: str) -> ReportRendererError:
        return cls(cls.Kind.UNEXPECTED, message)


class DialogueAssemblerPort(Protocol):
    def assemble(
        self,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> SynchronizedDialogue: ...


class ModelAudio(NamedTuple):
    path: str


class ModelAudioStager(Protocol):
    async def stage(self, recording_id: RecordingId, audio: AudioBlob) -> ModelAudio: ...


class JobRepository(ABC):
    @abstractmethod
    async def save(self, job: CallProcessingJob) -> None:
        """Сохранить (upsert) состояние job."""

    @abstractmethod
    async def get(self, job_id: str) -> CallProcessingJob | None:
        """Прочитать job по идентификатору или `None`."""

    @abstractmethod
    async def delete(self, job_id: str) -> None:
        """Удалить job, если он существует."""

    @abstractmethod
    async def list_by_status(self, status: JobStatus) -> Sequence[CallProcessingJob]:
        """Список job в указанном статусе."""


class ArtifactStore(ABC):
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
    async def load_diarization(self, recording_id: RecordingId) -> DiarizedTranscript | None: ...

    @abstractmethod
    async def save_emotion(self, emotion: EmotionAnalysis) -> None: ...

    @abstractmethod
    async def load_emotion(self, recording_id: RecordingId) -> EmotionAnalysis | None: ...

    @abstractmethod
    async def save_report(self, report: CallReport) -> None: ...

    @abstractmethod
    async def load_report(self, recording_id: RecordingId) -> CallReport | None: ...

    @abstractmethod
    async def save_report_pdf(self, recording_id: RecordingId, content: bytes) -> None: ...

    @abstractmethod
    async def load_report_pdf(self, recording_id: RecordingId) -> bytes | None: ...

    @abstractmethod
    async def delete_outputs(self, recording_id: RecordingId) -> None:
        """Delete derived pipeline artifacts while keeping source recordings intact."""


class RecordingInbox(ABC):
    @abstractmethod
    async def save_wav(self, filename: str, content: bytes) -> CallRecording:
        """Persist an uploaded WAV file and return its recording metadata."""


class ProcessingQueueError(Exception):
    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: ProcessingQueueError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> ProcessingQueueError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> ProcessingQueueError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def unexpected(cls, message: str) -> ProcessingQueueError:
        return cls(cls.Kind.UNEXPECTED, message)


class ProcessingMessage(NamedTuple):
    recording_id: RecordingId
    delivery_tag: str


class ProcessingQueue(ABC):
    @abstractmethod
    async def publish(self, recording_id: RecordingId) -> None:
        """Publish a recording id for asynchronous processing."""

    @abstractmethod
    async def get(self) -> ProcessingMessage | None:
        """Return one message or None when the queue is empty."""

    @abstractmethod
    async def ack(self, message: ProcessingMessage) -> None:
        """Mark a message as successfully processed."""

    @abstractmethod
    async def reject(self, message: ProcessingMessage, requeue: bool) -> None:
        """Reject a message after failed processing."""


__all__ = [
    "ArtifactStore",
    "CallRecordingSource",
    "CallRecordingSourceError",
    "DialogueAssemblerPort",
    "EmotionRecognizer",
    "EmotionRecognizerError",
    "JobRepository",
    "ModelAudio",
    "ModelAudioStager",
    "Period",
    "ProcessingMessage",
    "ProcessingQueue",
    "ProcessingQueueError",
    "RecordingInbox",
    "ReportGenerator",
    "ReportGeneratorError",
    "ReportRenderer",
    "ReportRendererError",
    "SpeakerDiarizer",
    "SpeakerDiarizerError",
    "Transcriber",
    "TranscriberError",
]
