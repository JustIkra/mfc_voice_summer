from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from call_analytics.service.ports import (
    ArtifactStore,
    CallProcessingPipeline,
    CallRecordingSource,
    CallRecordingSourceError,
    CallRepository,
    EmotionRecognizer,
    EmotionRecognizerError,
    FinalReportRepository,
    JobRepository,
    RecordingWorkspace,
    ReportGenerator,
    ReportGeneratorError,
    ReportRenderer,
    ReportRendererError,
    SpeakerDiarizer,
    SpeakerDiarizerError,
    Transcriber,
    TranscriberError,
)
from domain import (
    AudioBlob,
    CallProcessingJob,
    CallRecording,
    FinalReportDocument,
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
    ReportRendererError,
)


class _StageExecutionError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        super().__init__(message)


class _EmptyRecordingError(Exception):
    pass


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
        report_renderer: ReportRenderer | None = None,
        calls: CallRepository | None = None,
        final_reports: FinalReportRepository | None = None,
        workspace: RecordingWorkspace | None = None,
    ) -> None:
        self._source = source
        self._transcriber = transcriber
        self._diarizer = diarizer
        self._emotion_recognizer = emotion_recognizer
        self._report_generator = report_generator
        self._jobs = jobs
        self._artifacts = artifacts
        self._clock = clock
        self._report_renderer = report_renderer
        self._calls = calls
        self._final_reports = final_reports
        self._workspace = workspace

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
            document = await self._execute(stage, job.recording_id)
        except _EmptyRecordingError:
            job = job.skip_empty()
            await self._jobs.save(job)
            if self._calls is not None:
                await self._calls.mark_skipped_empty(
                    job.recording_id,
                    "ASR did not find recognizable speech",
                )
            await self._cleanup(job.recording_id)
            return job
        except _PORT_ERRORS as error:
            job = job.fail_stage(stage, error.kind.name, str(error))
            await self._jobs.save(job)
            await self._cleanup(job.recording_id)
            return job
        except _StageExecutionError as error:
            job = job.fail_stage(stage, error.kind, str(error))
            await self._jobs.save(job)
            await self._cleanup(job.recording_id)
            return job

        job = job.complete_stage(stage)
        if document is not None and self._final_reports is not None:
            await self._final_reports.finalize(job, document)
        else:
            await self._jobs.save(job)
        if job.status is JobStatus.DONE:
            await self._cleanup(job.recording_id)
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
        job = job.restart() if self._workspace is not None else job.retry()
        await self._jobs.save(job)
        return job

    async def cancel(self, job_id: str) -> CallProcessingJob:
        job = (await self._require_job(job_id)).cancel()
        await self._jobs.save(job)
        await self._cleanup(job.recording_id)
        return job

    async def resume(self, job_id: str) -> CallProcessingJob:
        job = (await self._require_job(job_id)).resume()
        await self._jobs.save(job)
        return job

    async def _execute(
        self,
        stage: JobStage,
        recording_id: RecordingId,
    ) -> FinalReportDocument | None:
        if stage is JobStage.TRANSCRIBE:
            audio = await self._fetch_audio(recording_id)
            transcript = await self._transcriber.transcribe(recording_id, audio)
            if not transcript.full_text.strip():
                raise _EmptyRecordingError
            await self._artifacts.save_transcript(transcript)
        elif stage is JobStage.DIARIZE:
            audio = await self._fetch_audio(recording_id)
            stored_transcript = await self._artifacts.load_transcript(recording_id)
            if stored_transcript is None:
                raise _StageExecutionError(
                    "MISSING_ARTIFACT", f"артефакт transcript отсутствует для {recording_id.value}"
                )
            diarized = await self._diarizer.diarize(audio, stored_transcript)
            await self._artifacts.save_diarization(diarized)
        elif stage is JobStage.EMOTION:
            audio = await self._fetch_audio(recording_id)
            stored_diarized = await self._artifacts.load_diarization(recording_id)
            if stored_diarized is None:
                raise _StageExecutionError(
                    "MISSING_ARTIFACT", f"артефакт diarization отсутствует для {recording_id.value}"
                )
            emotion = await self._emotion_recognizer.recognize(audio, stored_diarized)
            await self._artifacts.save_emotion(emotion)
        elif stage is JobStage.REPORT:
            stored_transcript = await self._artifacts.load_transcript(recording_id)
            stored_diarized = await self._artifacts.load_diarization(recording_id)
            stored_emotion = await self._artifacts.load_emotion(recording_id)
            if stored_transcript is None or stored_diarized is None or stored_emotion is None:
                raise _StageExecutionError(
                    "MISSING_ARTIFACT",
                    "артефакты transcript/diarization/emotion отсутствуют "
                    f"для {recording_id.value}",
                )
            report = await self._report_generator.generate(
                stored_transcript, stored_diarized, stored_emotion
            )
            if self._final_reports is not None:
                recording = await self._load_recording(recording_id)
                return FinalReportDocument(
                    recording=recording,
                    report=report,
                    transcript=stored_transcript,
                    diarized=stored_diarized,
                    emotions=stored_emotion,
                )
            await self._artifacts.save_report(report)
            if self._report_renderer is not None:
                pdf = await self._report_renderer.render(
                    report,
                    stored_transcript,
                    stored_diarized,
                    stored_emotion,
                )
                await self._artifacts.save_report_pdf(recording_id, pdf)
        return None

    async def _fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        return await self._source.fetch_audio(recording_id)

    async def _load_recording(self, recording_id: RecordingId) -> CallRecording:
        recording = (
            await self._calls.load_recording(recording_id)
            if self._calls is not None
            else await self._artifacts.load_recording(recording_id)
        )
        if recording is None:
            raise _StageExecutionError(
                "MISSING_RECORDING",
                f"метаданные записи отсутствуют для {recording_id.value}",
            )
        return recording

    async def _cleanup(self, recording_id: RecordingId) -> None:
        if self._workspace is not None:
            await self._workspace.clear(recording_id)

    async def _require_job(self, job_id: str) -> CallProcessingJob:
        job = await self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"job {job_id} не найден")
        return job


__all__ = ["CallProcessingService"]
