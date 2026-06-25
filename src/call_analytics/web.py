from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from call_analytics.bootstrap import build_application
from call_analytics.report_view import report_to_public_json
from call_analytics.service.workspace import (
    JobNotFound,
    PipelineWorkspace,
    RecordingNotFound,
    RecordingUploadUnavailable,
)
from domain import (
    STAGE_ORDER,
    CallProcessingJob,
    CallRecording,
    CallReport,
    JobStage,
    RecordingId,
)

_STATIC_DIR = Path(__file__).parent / "web_static"


@dataclass(slots=True)
class _State:
    factory: Callable[[], PipelineWorkspace]
    workspace: PipelineWorkspace | None = None


def create_app(factory: Callable[[], PipelineWorkspace] | None = None) -> FastAPI:
    state = _State(factory=factory or _build_workspace)
    app = FastAPI(title="MFC Voice Pipeline", version="0.1.0")

    def workspace() -> PipelineWorkspace:
        if state.workspace is None:
            state.workspace = state.factory()
        return state.workspace

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/recordings")
    async def list_recordings() -> list[dict[str, Any]]:
        return [
            _recording_to_json(item.recording, item.job)
            for item in await workspace().list_recordings()
        ]

    @app.post("/api/recordings", status_code=201)
    async def upload_recording(
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        if file.filename is None or not file.filename.lower().endswith(".wav"):
            raise HTTPException(status_code=400, detail="загрузите запись в формате .wav")
        try:
            item = await workspace().upload_recording(file.filename, await file.read())
            job = await workspace().enqueue_recording(item.recording.id)
        except RecordingUploadUnavailable as error:
            raise HTTPException(status_code=501, detail="upload is not configured") from error
        return _recording_to_json(item.recording, job)

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        try:
            return _job_to_json(await workspace().get_job(job_id))
        except JobNotFound as error:
            raise HTTPException(status_code=404, detail="job not found") from error

    @app.websocket("/api/jobs/{job_id}/events")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        try:
            while True:
                try:
                    job = await workspace().get_job(job_id)
                except JobNotFound:
                    await websocket.close(code=1008, reason="job not found")
                    return
                await websocket.send_json(_job_to_json(job))
                if job.status.value in {"done", "failed"}:
                    return
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            return

    @app.post("/api/recordings/{recording_id}/jobs", status_code=201)
    async def enqueue_recording(recording_id: str) -> dict[str, Any]:
        try:
            job = await workspace().enqueue_recording(RecordingId(recording_id))
        except RecordingNotFound as error:
            raise HTTPException(status_code=404, detail="recording not found") from error
        return _job_to_json(job)

    @app.post("/api/jobs/{job_id}/retry")
    async def retry_job(job_id: str) -> dict[str, Any]:
        try:
            return _job_to_json(await workspace().retry_job(job_id))
        except JobNotFound as error:
            raise HTTPException(status_code=404, detail="job not found") from error

    @app.get("/api/jobs/{job_id}/report")
    async def get_report(job_id: str) -> dict[str, Any]:
        report = await workspace().load_report(RecordingId(job_id))
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        return _report_to_json(report)

    @app.get("/api/jobs/{job_id}/report.pdf")
    async def get_report_pdf(job_id: str) -> Response:
        content = await workspace().load_report_pdf(RecordingId(job_id))
        if content is None:
            raise HTTPException(status_code=404, detail="report pdf not found")
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{job_id}.pdf"'},
        )

    if _STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(_STATIC_DIR / "index.html")

    return app


def _build_workspace() -> PipelineWorkspace:
    return build_application().workspace


def _recording_to_json(
    recording: CallRecording,
    job: CallProcessingJob | None,
) -> dict[str, Any]:
    return {
        "id": recording.id.value,
        "filename": str(recording.metadata.get("filename", f"{recording.id.value}.wav")),
        "started_at": recording.started_at.isoformat(),
        "duration_seconds": recording.duration.total_seconds(),
        "channel_layout": recording.channel_layout.name,
        "job": _job_to_json(job) if job is not None else None,
    }


def _job_to_json(job: CallProcessingJob) -> dict[str, Any]:
    completed = [stage for stage in STAGE_ORDER if stage in job.completed_stages]
    next_stage = job.next_stage()
    return {
        "id": job.id,
        "recording_id": job.recording_id.value,
        "status": job.status.value,
        "completed_stages": [stage.value for stage in completed],
        "next_stage": next_stage.value if isinstance(next_stage, JobStage) else None,
        "attempts": {stage.value: count for stage, count in job.attempts.items()},
        "last_error": list(job.last_error) if job.last_error is not None else None,
        "created_at": job.created_at.isoformat(),
    }


def _report_to_json(report: CallReport) -> dict[str, Any]:
    return report_to_public_json(report)


app = create_app()

__all__ = ["app", "create_app"]
