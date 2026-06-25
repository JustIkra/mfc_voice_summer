# Runtime Pipeline

## Purpose

This document describes the production-oriented shape of the call analytics pipeline after moving temporary scripts into ports, services, and adapters.

## Process Boundaries

The pipeline is not responsible for model lifecycle management. ML and LLM services are long-running processes:

- `asr-api` exposes `/transcribe`;
- `diarization-api` exposes `/diarize`;
- `emotion-api` exposes `/emotion`;
- Qwen/vLLM exposes `/v1/chat/completions`;
- RabbitMQ stores recording-processing commands.

The application layer calls these services through ports. If a service is unavailable, the relevant port raises a contract error and the job is left retryable.

## Queue Strategy

RabbitMQ is the default queue backend because recording processing is a long-running command workflow. A worker must acknowledge a message only after the job reaches `DONE`; failed jobs are rejected with requeue enabled by default.

Kafka is intentionally not implemented yet. It should be added as another adapter only if the system needs replayable event streams, audit logs, or high-throughput downstream analytics.

## Application Composition

`call_analytics.bootstrap.build_application()` wires:

- `LocalDirectoryRecordingSource`;
- `LocalJobRepository`;
- `LocalArtifactStore`;
- `RabbitMQProcessingQueue`;
- `VoiceModelTranscriber`;
- `VoiceModelDiarizer`;
- `VoiceModelEmotionRecognizer`;
- `QwenReportGenerator`;
- `ReportLabReportRenderer`;
- `CallProcessingService`;
- `ProcessingWorker`.

Future FastAPI routes should depend on this composition root through lifespan/application state, not construct adapters inside route functions.

## Report Contract

The final report includes:

- whether the issue was resolved;
- client satisfaction;
- emotional assessment;
- evidence;
- risks;
- recommendations;
- summary.

The Qwen prompt includes synchronized utterances with ASR confidence, diarization coverage, and SER emotion episodes. It does not disable thinking; final JSON is parsed only from the assistant `content`.

## Artifacts

Artifacts are persisted under `VOICE_ARTIFACTS_DIR`:

- `recordings/*.recording.json`;
- `transcripts/*.transcript.json`;
- `diarization/*.diarization.json`;
- `emotions/*.emotion.json`;
- `reports/*.report.json`;
- `reports/*.pdf`.

This layout allows retries without recomputing earlier successful stages.
