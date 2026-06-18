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
            stored_transcript = await self._artifacts.load_transcript(recording_id)
            assert stored_transcript is not None
            diarized = await self._diarizer.diarize(audio, stored_transcript)
            await self._artifacts.save_diarization(diarized)
        elif stage is JobStage.EMOTION:
            audio = await self._fetch_audio(recording_id)
            stored_diarized = await self._artifacts.load_diarization(recording_id)
            assert stored_diarized is not None
            emotion = await self._emotion_recognizer.recognize(audio, stored_diarized)
            await self._artifacts.save_emotion(emotion)
        elif stage is JobStage.REPORT:
            stored_diarized = await self._artifacts.load_diarization(recording_id)
            stored_emotion = await self._artifacts.load_emotion(recording_id)
            assert stored_diarized is not None and stored_emotion is not None
            report = await self._report_generator.generate(
                stored_diarized, stored_emotion
            )
            await self._artifacts.save_report(report)

    async def _fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        return await self._source.fetch_audio(recording_id)

    async def _require_job(self, job_id: str) -> CallProcessingJob:
        job = await self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"job {job_id} не найден")
        return job


__all__ = ["CallProcessingService"]
