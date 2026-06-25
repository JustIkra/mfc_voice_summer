# Clean Pipeline Runtime Design

## Goal

Move the real voice analytics pipeline out of temporary scripts into the existing clean architecture structure, prepare the application boundary for a future web API, and keep ML/LLM services as persistent Docker-hosted HTTP runtimes independent from pipeline execution.

## Architecture

The project already has the right base shape: `domain`, `call_analytics.service`, `call_analytics.infra.ports`, and `call_analytics.infra.adapters`. The migration keeps `CallProcessingService` as the orchestration use case and moves concrete ASR, diarization, emotion, Qwen, artifact, PDF, and queue integrations behind ports/adapters.

Runtime processes are separated:

- Model services: long-running Docker containers exposing HTTP APIs.
- Worker: consumes recording jobs from a queue and runs `CallProcessingService`.
- CLI/web entrypoints: enqueue work and query job/artifact state through an application container.

## Queue Choice

Use RabbitMQ first. It matches the current workload: long-running recording processing, explicit ack/nack after a job completes, retry/dead-letter handling, and simple operational control. Kafka stays as a future adapter to the same queue/event port if replayable event streams or higher-throughput analytics become necessary.

## Components

- `domain`: enrich `CallReport` with question resolution, client satisfaction, emotional assessment, evidence, risks, and recommendations. Add word-level transcript data so the dialogue builder can preserve ASR timestamps.
- `infra/ports`: add ports for processing queue, report rendering, model health checks, and keep current compute/persistence ports stable.
- `infra/adapters/model_api`: HTTP clients for persistent ASR, diarization, emotion, and Qwen services.
- `infra/adapters/reporting`: PDF renderer that writes a final PDF tied to `<recording>.wav`.
- `infra/adapters/queue`: in-memory queue for tests/local runs, RabbitMQ adapter for production, Kafka reserved for future adapter.
- `service`: add dialogue assembly and worker/ingestion services around the existing pipeline. The pipeline never starts or stops ML containers.
- `bootstrap`: composition root that wires ports/adapters from settings so CLI, worker, and future FastAPI routes share the same object graph.
- `docker-compose.voice.yml`: run model APIs as persistent services with restart policies and health checks.

## Data Flow

1. Local directory source discovers `*.wav` recordings.
2. Ingestion creates a job and publishes its recording id.
3. Worker receives a queue message, runs the pipeline, and acknowledges only after the job reaches `DONE`.
4. Pipeline stages call persistent HTTP model services and persist intermediate artifacts.
5. Report generation sends synchronized dialogue, role hints, ASR confidence, and emotion episodes to Qwen.
6. Report renderer writes JSON/PDF artifacts named by the original WAV stem.

## Error Handling

Model connection, timeout, invalid format, rate limit, and server failures remain port-level errors. The service records failed stage state and keeps previous artifacts for retry. Queue adapters acknowledge only successful jobs, reject/requeue transient failures, and can route exhausted messages to a dead-letter queue.

## Testing

Use TDD for migration:

- Preserve existing service tests.
- Move temporary script tests into focused tests for dialogue assembly, Qwen JSON extraction, prompt payload, and PDF/report renderer behavior.
- Add in-memory queue/worker tests.
- Add adapter mapping tests with fake HTTP transports rather than real models.
- Keep Docker/model runtime verified by health checks and integration commands, not unit tests.

## Out Of Scope

- Building the actual web UI/API routes.
- Implementing Kafka adapter now.
- Starting/stopping ML models from the pipeline.
- Replacing the selected SOTA model choices.
