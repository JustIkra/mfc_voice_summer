# Recording Filters, Uploads, and Queue Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add status filters, restore the upload/search/pagination controls, make uploads writable through an `.env`-configured isolated directory, and let operators requeue or cancel stuck pending jobs.

**Architecture:** Keep `/media/audio` read-only and mount a separate uploads directory below `/data/recordings/uploads`. Represent queue cancellation as a persisted `canceled` job state so stale RabbitMQ messages can be acknowledged safely. Keep filtering client-side with a single active status combined with the existing search and pagination.

**Tech Stack:** Python 3.12, FastAPI, pytest, RabbitMQ/aio-pika, Docker Compose, vanilla JavaScript, CSS.

## Global Constraints

- Moscow time remains the project default.
- Preserve the local page title `MFC Voice`.
- Preserve upload, search, pagination, and live status controls.
- `/media/audio` remains read-only in every container.
- `web` alone gets read-write access to `${VOICE_UPLOADS_HOST_DIR:-./.uploads}`.
- `worker` gets read-only access to the uploads directory.
- Filters are `Все`, `Ошибки`, `В очереди`, `В работе`, `Готово`, `Без запуска`.
- `Без запуска` includes records without a job and jobs with status `canceled`.
- Search and status filters combine with AND and reset pagination to page 1.
- Do not introduce a breakpoint outside the existing `1200px` and `767px` breakpoints.
- Do not overwrite unrelated user changes in `.memory-base/index.md`.
- Use TDD for every behavior change.

---

### Task 1: Add the canceled job state and safe worker behavior

**Files:**
- Modify: `src/domain/job.py`
- Modify: `src/call_analytics/service/ports/pipeline.py`
- Modify: `src/call_analytics/service/pipeline.py`
- Modify: `src/call_analytics/service/worker.py`
- Test: `tests/domain/test_job.py`
- Test: `tests/call_analytics/service/test_processing_worker.py`

**Interfaces:**
- Produces: `JobStatus.CANCELED`
- Produces: `CallProcessingJob.cancel() -> CallProcessingJob`
- Produces: `CallProcessingJob.resume() -> CallProcessingJob`
- Produces: `CallProcessingPipeline.cancel(job_id: str) -> CallProcessingJob`
- Produces: `CallProcessingPipeline.resume(job_id: str) -> CallProcessingJob`
- Worker acknowledges messages whose resulting status is `DONE` or `CANCELED`.

- [ ] **Step 1: Write failing domain tests**

Add to `tests/domain/test_job.py`:

```python
def test_pending_job_can_be_canceled_and_resumed() -> None:
    canceled = _job().cancel()

    assert canceled.status is JobStatus.CANCELED
    assert canceled.next_stage() is JobStage.TRANSCRIBE

    resumed = canceled.resume()
    assert resumed.status is JobStatus.PENDING
    assert resumed.completed_stages == canceled.completed_stages


def test_only_pending_job_can_be_canceled() -> None:
    running = _job().start_stage(JobStage.TRANSCRIBE)

    with pytest.raises(InvalidJobTransition):
        running.cancel()


def test_only_canceled_job_can_be_resumed() -> None:
    with pytest.raises(InvalidJobTransition):
        _job().resume()
```

- [ ] **Step 2: Run domain tests and verify failure**

Run:

```bash
pytest -q tests/domain/test_job.py
```

Expected: failures because `CANCELED`, `cancel`, and `resume` do not exist.

- [ ] **Step 3: Implement domain transitions**

In `src/domain/job.py`, add:

```python
class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"
```

Add to `CallProcessingJob`:

```python
def cancel(self) -> CallProcessingJob:
    if self.status is not JobStatus.PENDING:
        raise InvalidJobTransition(
            f"отмена возможна только из PENDING, текущий {self.status.name}"
        )
    return replace(self, status=JobStatus.CANCELED)

def resume(self) -> CallProcessingJob:
    if self.status is not JobStatus.CANCELED:
        raise InvalidJobTransition(
            f"возврат в очередь возможен только из CANCELED, текущий {self.status.name}"
        )
    return replace(self, status=JobStatus.PENDING, last_error=None)
```

- [ ] **Step 4: Add failing service and worker tests**

Extend the test `FailingPipeline` in `tests/call_analytics/service/test_processing_worker.py` with `cancel` and `resume` methods that raise `AssertionError`.

Add:

```python
async def test_worker_acknowledges_canceled_job_without_processing_stages() -> None:
    queue = InMemoryProcessingQueue()
    jobs = InMemoryJobRepository()
    artifacts = InMemoryArtifactStore()
    pipeline = CallProcessingService(
        source=FakeRecordingSource(
            {RID.value: AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)}
        ),
        transcriber=NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: NOW,
    )
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=1),
        channel_layout=ChannelLayout.STEREO,
    )
    job = await pipeline.enqueue(recording)
    await pipeline.cancel(job.id)
    await queue.publish(RID)

    processed = await ProcessingWorker(queue, pipeline, jobs).run_once()

    assert processed is True
    assert queue.acked == (RID.value,)
    assert queue.rejected == ()
    assert await artifacts.load_transcript(RID) is None
```

- [ ] **Step 5: Run worker test and verify failure**

Run:

```bash
pytest -q tests/call_analytics/service/test_processing_worker.py
```

Expected: failure because pipeline cancel/resume and canceled acknowledgement are absent.

- [ ] **Step 6: Implement service transitions and worker acknowledgement**

Add these abstract methods to `CallProcessingPipeline`:

```python
@abstractmethod
async def cancel(self, job_id: str) -> CallProcessingJob:
    """Cancel a pending job."""

@abstractmethod
async def resume(self, job_id: str) -> CallProcessingJob:
    """Return a canceled job to pending."""
```

Implement in `CallProcessingService`:

```python
async def cancel(self, job_id: str) -> CallProcessingJob:
    job = (await self._require_job(job_id)).cancel()
    await self._jobs.save(job)
    return job

async def resume(self, job_id: str) -> CallProcessingJob:
    job = (await self._require_job(job_id)).resume()
    await self._jobs.save(job)
    return job
```

Change the worker result branch to:

```python
if job.status in {JobStatus.DONE, JobStatus.CANCELED}:
    await self._queue.ack(message)
else:
    await self._queue.reject(message, requeue=self._requeue_failed)
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
pytest -q tests/domain/test_job.py tests/call_analytics/service/test_processing_worker.py tests/call_analytics/service/test_call_processing_service.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit the domain and worker change**

```bash
git add src/domain/job.py src/call_analytics/service/ports/pipeline.py src/call_analytics/service/pipeline.py src/call_analytics/service/worker.py tests/domain/test_job.py tests/call_analytics/service/test_processing_worker.py
git commit -m "Add safe queue cancellation state"
```

---

### Task 2: Expose pending requeue and cancellation through workspace and API

**Files:**
- Modify: `src/call_analytics/service/workspace.py`
- Modify: `src/call_analytics/web.py`
- Modify: `tests/call_analytics/service/test_workspace.py`
- Modify: `tests/call_analytics/test_web.py`

**Interfaces:**
- Produces: `JobQueueConflict(job_id: str, status: JobStatus)`
- Produces: `PipelineWorkspace.requeue_pending_job(job_id: str) -> CallProcessingJob`
- Produces: `PipelineWorkspace.cancel_pending_job(job_id: str) -> CallProcessingJob`
- Consumes: `CallProcessingPipeline.cancel` and `CallProcessingPipeline.resume` from Task 1.
- Produces: `POST /api/jobs/{job_id}/requeue`
- Produces: `POST /api/jobs/{job_id}/cancel`

- [ ] **Step 1: Write failing workspace tests**

Add to `tests/call_analytics/service/test_workspace.py`:

```python
async def test_requeue_pending_job_publishes_another_message() -> None:
    workspace, queue, _ = build_workspace()
    await workspace.enqueue_recording(RecordingId("call-001"))

    job = await workspace.requeue_pending_job("call-001")

    assert job.status is JobStatus.PENDING
    assert [item.value for item in queue.published] == ["call-001", "call-001"]


async def test_cancel_pending_job_and_enqueue_again() -> None:
    workspace, queue, _ = build_workspace()
    await workspace.enqueue_recording(RecordingId("call-001"))

    canceled = await workspace.cancel_pending_job("call-001")
    resumed = await workspace.enqueue_recording(RecordingId("call-001"))

    assert canceled.status is JobStatus.CANCELED
    assert resumed.status is JobStatus.PENDING
    assert [item.value for item in queue.published] == ["call-001", "call-001"]


async def test_requeue_and_cancel_reject_non_pending_job() -> None:
    workspace, _, _ = build_workspace()
    await workspace.enqueue_recording(RecordingId("call-001"))
    await workspace.process_recording(RecordingId("call-001"))

    with pytest.raises(JobQueueConflict):
        await workspace.requeue_pending_job("call-001")
    with pytest.raises(JobQueueConflict):
        await workspace.cancel_pending_job("call-001")
```

Import `JobStatus` and `JobQueueConflict`.

- [ ] **Step 2: Run workspace tests and verify failure**

Run:

```bash
pytest -q tests/call_analytics/service/test_workspace.py
```

Expected: failures because the conflict and methods do not exist.

- [ ] **Step 3: Implement workspace methods**

Add:

```python
class JobQueueConflict(Exception):
    def __init__(self, job_id: str, status: JobStatus) -> None:
        self.status = status
        super().__init__(f"job {job_id} has status {status.value}")
```

Implement:

```python
async def requeue_pending_job(self, job_id: str) -> CallProcessingJob:
    job = await self.get_job(job_id)
    if job.status is not JobStatus.PENDING:
        raise JobQueueConflict(job_id, job.status)
    await self._queue.publish(job.recording_id)
    return job

async def cancel_pending_job(self, job_id: str) -> CallProcessingJob:
    job = await self.get_job(job_id)
    if job.status is not JobStatus.PENDING:
        raise JobQueueConflict(job_id, job.status)
    return await self._pipeline.cancel(job_id)
```

Update `enqueue_recording`:

```python
if existing is None:
    job = await self._pipeline.enqueue(recording)
elif existing.status is JobStatus.CANCELED:
    job = await self._pipeline.resume(existing.id)
else:
    job = existing
await self._queue.publish(recording_id)
```

Export `JobQueueConflict`.

- [ ] **Step 4: Write failing API tests**

Add to `tests/call_analytics/test_web.py`:

```python
def test_pending_job_can_be_requeued_and_canceled() -> None:
    client, queue, _ = build_client()
    client.post("/api/recordings/call-001/jobs")

    requeued = client.post("/api/jobs/call-001/requeue")
    canceled = client.post("/api/jobs/call-001/cancel")

    assert requeued.status_code == 200
    assert requeued.json()["status"] == "pending"
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    assert [item.value for item in queue.published] == ["call-001", "call-001"]


def test_queue_actions_return_conflict_after_processing() -> None:
    client, _, _ = build_client()
    client.post("/api/recordings/call-001/jobs")
    client.post("/api/jobs/call-001/cancel")

    assert client.post("/api/jobs/call-001/requeue").status_code == 409
    assert client.post("/api/jobs/call-001/cancel").status_code == 409
```

- [ ] **Step 5: Run API tests and verify failure**

Run:

```bash
pytest -q tests/call_analytics/test_web.py
```

Expected: 404 for both new routes.

- [ ] **Step 6: Implement API routes and serialization**

Import `JobQueueConflict` and add:

```python
@app.post("/api/jobs/{job_id}/requeue")
async def requeue_pending_job(job_id: str) -> dict[str, Any]:
    try:
        return _job_to_json(await workspace().requeue_pending_job(job_id))
    except JobNotFound as error:
        raise HTTPException(status_code=404, detail="job not found") from error
    except JobQueueConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

@app.post("/api/jobs/{job_id}/cancel")
async def cancel_pending_job(job_id: str) -> dict[str, Any]:
    try:
        return _job_to_json(await workspace().cancel_pending_job(job_id))
    except JobNotFound as error:
        raise HTTPException(status_code=404, detail="job not found") from error
    except JobQueueConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
```

No serializer branch is required because `_job_to_json` emits `job.status.value`.

- [ ] **Step 7: Run focused service/API tests**

Run:

```bash
pytest -q tests/call_analytics/service/test_workspace.py tests/call_analytics/test_web.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit workspace and API changes**

```bash
git add src/call_analytics/service/workspace.py src/call_analytics/web.py tests/call_analytics/service/test_workspace.py tests/call_analytics/test_web.py
git commit -m "Add pending queue controls"
```

---

### Task 3: Make uploads use an isolated `.env`-configured directory

**Files:**
- Modify: `src/call_analytics/bootstrap.py`
- Modify: `src/call_analytics/infra/adapters/local_dir/recording_inbox.py`
- Modify: `docker-compose.voice.yml`
- Create: `docker-compose.prod.yml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`
- Test: `tests/call_analytics/test_bootstrap.py`
- Test: `tests/call_analytics/infra/adapters/test_local_dir.py`
- Test: `tests/call_analytics/test_docker_config.py`

**Interfaces:**
- Produces: `AppSettings.uploads_dir: Path`
- Produces: `VOICE_UPLOADS_DIR`
- Produces: `VOICE_UPLOADS_HOST_DIR`
- Changes: `LocalDirectoryRecordingInbox(directory: Path, recording_root: Path | None = None)`

- [ ] **Step 1: Write failing inbox and settings tests**

Add to `tests/call_analytics/infra/adapters/test_local_dir.py`:

```python
async def test_recording_inbox_uses_recording_root_for_nested_upload_id(
    tmp_path: Path,
) -> None:
    recordings = tmp_path / "recordings"
    uploads = recordings / "uploads"
    source_wav = tmp_path / "source.wav"
    _make_wav(source_wav, nchannels=1)
    inbox = LocalDirectoryRecordingInbox(uploads, recording_root=recordings)

    recording = await inbox.save_wav("new-call.wav", source_wav.read_bytes())
    source = LocalDirectoryRecordingSource(recordings)
    blob = await source.fetch_audio(recording.id)

    assert recording.id.value.startswith("rel-")
    assert recording.metadata["filename"] == "uploads/new-call.wav"
    assert blob.data == source_wav.read_bytes()
```

Extend `test_settings_from_env_uses_local_defaults`:

```python
monkeypatch.setenv("VOICE_UPLOADS_DIR", str(tmp_path / "input" / "uploads"))
assert settings.uploads_dir == tmp_path / "input" / "uploads"
```

Pass `uploads_dir=tmp_path / "recordings" / "uploads"` in the explicit `AppSettings` construction.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
pytest -q tests/call_analytics/infra/adapters/test_local_dir.py tests/call_analytics/test_bootstrap.py
```

Expected: constructor and settings failures.

- [ ] **Step 3: Implement upload path wiring**

Change the inbox constructor:

```python
def __init__(self, directory: Path, recording_root: Path | None = None) -> None:
    self._directory = directory
    self._recording_root = recording_root or directory
```

Use two sources in `save_wav`:

```python
validation_source = LocalDirectoryRecordingSource(self._directory)
recording_source = LocalDirectoryRecordingSource(self._recording_root)
temporary.write_bytes(content)
validation_source._to_recording(temporary)
target = self._link_to_next_available_path(temporary, safe_name)
return recording_source._to_recording(target)
```

Add to `AppSettings`:

```python
uploads_dir: Path = Path(".recordings/uploads")
```

Read:

```python
uploads_dir=Path(os.getenv("VOICE_UPLOADS_DIR", ".recordings/uploads")),
```

Wire:

```python
inbox = LocalDirectoryRecordingInbox(
    settings.uploads_dir,
    recording_root=settings.recordings_dir,
)
```

- [ ] **Step 4: Run inbox/settings tests**

Run:

```bash
pytest -q tests/call_analytics/infra/adapters/test_local_dir.py tests/call_analytics/test_bootstrap.py
```

Expected: all tests pass.

- [ ] **Step 5: Write failing Compose contract tests**

Add to `tests/call_analytics/test_docker_config.py`:

```python
def test_upload_mount_is_writable_only_in_web() -> None:
    compose = yaml.safe_load(Path("docker-compose.voice.yml").read_text(encoding="utf-8"))
    web_volumes = compose["services"]["web"]["volumes"]
    worker_volumes = compose["services"]["worker"]["volumes"]

    assert "${VOICE_UPLOADS_HOST_DIR:-./.uploads}:/data/recordings/uploads" in web_volumes
    assert (
        "${VOICE_UPLOADS_HOST_DIR:-./.uploads}:/data/recordings/uploads:ro"
        in worker_volumes
    )
    assert compose["services"]["web"]["environment"]["VOICE_UPLOADS_DIR"] == (
        "/data/recordings/uploads"
    )


def test_prod_recording_archive_remains_read_only() -> None:
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))

    for service_name in ("web", "worker"):
        assert "/media/audio:/data/recordings:ro" in compose["services"][service_name]["volumes"]
```

- [ ] **Step 6: Run Compose tests and verify failure**

Run:

```bash
pytest -q tests/call_analytics/test_docker_config.py
```

Expected: upload mount assertions fail.

- [ ] **Step 7: Implement Compose and environment configuration**

For `web` in `docker-compose.voice.yml`, add:

```yaml
environment:
  VOICE_UPLOADS_DIR: /data/recordings/uploads
volumes:
  - ${VOICE_UPLOADS_HOST_DIR:-./.uploads}:/data/recordings/uploads
```

For `worker`, add the same environment value and:

```yaml
- ${VOICE_UPLOADS_HOST_DIR:-./.uploads}:/data/recordings/uploads:ro
```

Create `docker-compose.prod.yml`:

```yaml
services:
  web:
    environment:
      VOICE_RECORDINGS_DIR: /data/recordings
      VOICE_UPLOADS_DIR: /data/recordings/uploads
      VOICE_STAGING_DIR: /data/staging
      VOICE_CONTAINER_STAGING_DIR: /data/staging
    volumes:
      - /media/audio:/data/recordings:ro
      - ${VOICE_UPLOADS_HOST_DIR:-./.uploads}:/data/recordings/uploads
      - ./.reports:/data/reports
      - ./.staging:/data/staging
  worker:
    environment:
      VOICE_RECORDINGS_DIR: /data/recordings
      VOICE_UPLOADS_DIR: /data/recordings/uploads
      VOICE_STAGING_DIR: /data/staging
      VOICE_CONTAINER_STAGING_DIR: /data/staging
    volumes:
      - /media/audio:/data/recordings:ro
      - ${VOICE_UPLOADS_HOST_DIR:-./.uploads}:/data/recordings/uploads:ro
      - ./.reports:/data/reports
      - ./.staging:/data/staging
  asr-api:
    volumes:
      - /media/audio:/data/recordings:ro
      - ./.staging:/data/staging:ro
      - ./model-cache:/models
  diarization-api:
    volumes:
      - /media/audio:/data/recordings:ro
      - ./.staging:/data/staging:ro
      - ./model-cache:/models
  emotion-api:
    volumes:
      - /media/audio:/data/recordings:ro
      - ./.staging:/data/staging:ro
      - ./model-cache:/models
  qwen-api:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["0"]
              capabilities: [gpu]
```

Add to `.env.example`:

```dotenv
VOICE_UPLOADS_DIR=.recordings/uploads
VOICE_UPLOADS_HOST_DIR=.uploads
```

Add `.uploads/` to `.gitignore`. Update README local inputs and Docker mounts to distinguish the read-only archive from uploads.

- [ ] **Step 8: Run configuration tests**

Run:

```bash
pytest -q tests/call_analytics/test_docker_config.py tests/call_analytics/test_bootstrap.py tests/call_analytics/infra/adapters/test_local_dir.py
```

Expected: all tests pass.

- [ ] **Step 9: Commit upload configuration**

```bash
git add .env.example .gitignore README.md docker-compose.voice.yml docker-compose.prod.yml src/call_analytics/bootstrap.py src/call_analytics/infra/adapters/local_dir/recording_inbox.py tests/call_analytics/test_bootstrap.py tests/call_analytics/infra/adapters/test_local_dir.py tests/call_analytics/test_docker_config.py
git commit -m "Isolate writable recording uploads"
```

---

### Task 4: Restore controls and add status filters and pending actions

**Files:**
- Modify: `src/call_analytics/web_static/index.html`
- Modify: `src/call_analytics/web_static/assets/app.js`
- Modify: `src/call_analytics/web_static/assets/app.css`
- Modify: `tests/call_analytics/test_web_static.py`

**Interfaces:**
- Produces DOM nodes: `#uploadButton`, `#wavInput`, `#recordingSearch`, `#liveStatus`, `#pagination`, `#statusFilters`
- Produces state: `statusFilter`
- Consumes API routes from Task 2.

- [ ] **Step 1: Write failing static UI tests**

Restore existing assertions for upload, search, and pagination, then add:

```python
def test_recordings_list_has_status_filters() -> None:
    html = Path("src/call_analytics/web_static/index.html").read_text(encoding="utf-8")
    script = Path("src/call_analytics/web_static/assets/app.js").read_text(encoding="utf-8")

    assert 'id="statusFilters"' in html
    for value in ("all", "failed", "pending", "running", "done", "not-started"):
        assert f'data-status-filter="{value}"' in script
    assert "statusFilter" in script
    assert "renderStatusFilters" in script
    assert 'aria-pressed="${active}"' in script


def test_pending_and_canceled_jobs_have_queue_actions() -> None:
    script = Path("src/call_analytics/web_static/assets/app.js").read_text(encoding="utf-8")

    assert 'data-action="requeue"' in script
    assert 'data-action="cancel"' in script
    assert "/requeue" in script
    assert "/cancel" in script
    assert 'job?.status === "canceled"' in script
    assert "отменено" in script
```

- [ ] **Step 2: Run static tests and verify failure**

Run:

```bash
pytest -q tests/call_analytics/test_web_static.py
```

Expected: failures for missing restored controls and filters.

- [ ] **Step 3: Restore the HTML controls and add a filter host**

Keep:

```html
<title>MFC Voice</title>
```

Restore the upload form in `.toolbar`, the `.panel-meta` search/live/updated controls, and `<div class="pagination" id="pagination" hidden></div>` from the committed layout.

Add between `.panel-header` and `.recordings`:

```html
<div class="status-filters" id="statusFilters" aria-label="Фильтр по статусу"></div>
```

- [ ] **Step 4: Implement filter state and rendering**

Add:

```javascript
const statusFilterOptions = [
  ["all", "Все"],
  ["failed", "Ошибки"],
  ["pending", "В очереди"],
  ["running", "В работе"],
  ["done", "Готово"],
  ["not-started", "Без запуска"],
];
```

Add `statusFilter: "all"` to state and `statusFiltersNode`.

Add click handling:

```javascript
statusFiltersNode.addEventListener("click", (event) => {
  const button = event.target.closest("[data-status-filter]");
  if (!button) return;
  state.statusFilter = button.dataset.statusFilter;
  state.currentPage = 1;
  syncSelectionToVisible();
  render();
});
```

Implement:

```javascript
function matchesStatus(recording) {
  if (state.statusFilter === "all") return true;
  if (state.statusFilter === "not-started") {
    return !recording.job || recording.job.status === "canceled";
  }
  return recording.job?.status === state.statusFilter;
}

function statusCounts() {
  const counts = Object.fromEntries(statusFilterOptions.map(([value]) => [value, 0]));
  counts.all = state.recordings.length;
  for (const recording of state.recordings) {
    if (!recording.job || recording.job.status === "canceled") counts["not-started"] += 1;
    else if (recording.job.status in counts) counts[recording.job.status] += 1;
  }
  return counts;
}

function renderStatusFilters() {
  const counts = statusCounts();
  statusFiltersNode.innerHTML = statusFilterOptions
    .map(([value, label]) => {
      const active = value === state.statusFilter;
      return `<button class="status-filter" type="button" data-status-filter="${value}" aria-pressed="${active}"><span>${label}</span><strong>${counts[value]}</strong></button>`;
    })
    .join("");
}
```

Update `visibleRecordings` so status is checked before the optional search query. Add:

```javascript
function syncSelectionToVisible() {
  const visible = visibleRecordings();
  if (!visible.some((item) => item.id === state.selectedId)) {
    state.selectedId = visible[0]?.id ?? null;
  }
}
```

Call it after search input changes and after refresh. Call `renderStatusFilters()` inside `render()`.

- [ ] **Step 5: Implement pending and canceled actions**

Add `canceled: "отменено"` to `statusLabels`.

Extend `runAction`:

```javascript
} else if (action === "requeue" && job?.status === "pending") {
  await requestJson(`/api/jobs/${encodeURIComponent(job.id)}/requeue`, {
    method: "POST",
  });
  showToast("Запись повторно отправлена в очередь");
} else if (action === "cancel" && job?.status === "pending") {
  if (!confirm("Удалить запись из очереди обработки?")) return;
  await requestJson(`/api/jobs/${encodeURIComponent(job.id)}/cancel`, {
    method: "POST",
  });
  showToast("Запись удалена из очереди");
```

Render pending buttons:

```javascript
${job?.status === "pending" ? '<button class="action secondary" type="button" data-action="requeue">Повторить очередь</button>' : ""}
${job?.status === "pending" ? '<button class="action danger" type="button" data-action="cancel">Удалить из очереди</button>' : ""}
${job?.status === "canceled" ? '<button class="action primary" type="button" data-action="enqueue">Поставить</button>' : ""}
```

Treat canceled as terminal in `isTerminalJob`.

- [ ] **Step 6: Style filters with existing tokens and breakpoints**

Add CSS:

```css
.status-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  padding: 0.7rem 1rem;
  border-bottom: 1px solid var(--line);
}

.status-filter {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 2rem;
  border: 1px solid var(--line);
  border-radius: 99rem;
  padding: 0.25rem 0.65rem;
  color: var(--muted);
  background: var(--paper);
  cursor: pointer;
}

.status-filter[aria-pressed="true"] {
  border-color: var(--signal);
  color: var(--signal);
  background: rgba(36, 87, 255, 0.08);
}

.status-filter strong {
  min-width: 1.35rem;
  border-radius: 99rem;
  padding: 0.1rem 0.35rem;
  color: inherit;
  background: rgba(102, 113, 127, 0.1);
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 0.72rem;
  text-align: center;
}
```

At `max-width: 767px`, make `.status-filters` horizontally scrollable with `flex-wrap: nowrap` and preserve button labels.

- [ ] **Step 7: Run UI tests**

Run:

```bash
pytest -q tests/call_analytics/test_web_static.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit UI changes**

```bash
git add src/call_analytics/web_static/index.html src/call_analytics/web_static/assets/app.js src/call_analytics/web_static/assets/app.css tests/call_analytics/test_web_static.py
git commit -m "Add recording status filters"
```

---

### Task 5: Full verification, documentation consistency, and prod readiness

**Files:**
- Verify all files changed by Tasks 1–4.
- Do not modify `.memory-base/index.md`.

**Interfaces:**
- Consumes the completed domain, API, upload, Compose, and UI behavior.

- [ ] **Step 1: Run the full Python test suite**

```bash
pytest -q
```

Expected: zero failures.

- [ ] **Step 2: Run Ruff checks**

```bash
ruff check .
ruff format --check .
```

Expected: both commands exit 0.

- [ ] **Step 3: Run type checking**

```bash
mypy src
```

Expected: exit 0.

- [ ] **Step 4: Validate Compose merge without exposing secrets**

```bash
docker compose -f docker-compose.voice.yml -f docker-compose.prod.yml config --quiet
```

Expected: exit 0.

Inspect only mount targets:

```bash
docker compose -f docker-compose.voice.yml -f docker-compose.prod.yml config --format json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print({name: service.get("volumes", []) for name, service in d["services"].items() if name in {"web", "worker"}})'
```

Expected: `/media/audio` is read-only for both; uploads is read-write for `web` and read-only for `worker`.

- [ ] **Step 5: Review the working tree**

```bash
git status --short
git diff --check
git log -6 --oneline
```

Expected: `.memory-base/index.md` remains an unrelated user modification; implementation files are committed; no whitespace errors exist.

- [ ] **Step 6: Report deployment command and current prod state**

Use:

```bash
pamsu docker compose -f docker-compose.voice.yml -f docker-compose.prod.yml up -d --build
```

After deployment, verify mounts, `/health`, upload, filters, pending controls, and the status distribution. Do not delete the test WAV because the API has no source-record deletion operation.
