# Обзор проекта: анализ звонков ИИ колл-центра (Naumen)

Clean-architecture (ports & adapters) для пайплайна обработки голосовых записей звонков из Naumen Contact Center:

```
Naumen (WAV/GSM0610) → TRANSCRIBE (whisper) → DIARIZE (оператор/клиент)
                     → EMOTION (SER) → REPORT (qwen: удовлетворённость + содержание)
```

## Слои

- `src/domain/` — чистые `@dataclass(frozen=True, slots=True)`, ноль инфра-зависимостей. Модели звонка/транскрипта/word timestamps/диаризации/эмоций/синхронизированного диалога/отчёта + машина состояний `CallProcessingJob` (стадии `TRANSCRIBE→DIARIZE→EMOTION→REPORT`, статусы `PENDING/RUNNING/DONE/FAILED`, ретрай только упавшей стадии). Граница — `domain/__init__.py` (`__all__`).
- `src/call_analytics/service/ports/` — application/use-case порты (`abc.ABC`) с контрактными ошибками `<Port>Error(Kind)`: `CallRecordingSource`, `Transcriber`, `SpeakerDiarizer`, `EmotionRecognizer`, `ReportGenerator`, `ReportRenderer`, `JobRepository`, `ArtifactStore`, `ProcessingQueue`. Старый `src/call_analytics/infra/ports/` оставлен как compatibility re-export.
- `src/call_analytics/infra/adapters/` — `noop/` (детерминированные compute-заглушки), `in_memory/` (репозитории/очередь для тестов), `local_dir/` (источник WAV, JSON/PDF artifacts, file-backed jobs), `model_api/` (persistent HTTP ASR/diarization/SER/Qwen adapters), `queue/` (RabbitMQ adapter), `reporting/` (ReportLab PDF renderer).
- `src/call_analytics/service/` — `CallProcessingService` оркестрирует стадии поверх портов; `DialogueAssembler` собирает word-level реплики с speaker coverage и emotion episodes; `ProcessingWorker` читает `ProcessingQueue` и ack/reject делает только после результата job.
- `src/call_analytics/bootstrap.py` — composition root для CLI/worker/future FastAPI lifespan: собирает local source/store/job repo, RabbitMQ queue, HTTP model adapters, Qwen report generator, PDF renderer.
- `docker-compose.voice.yml` — постоянные Docker services: RabbitMQ + ASR/diarization/emotion model API containers с healthcheck и `restart: unless-stopped`. Pipeline не стартует и не останавливает ML/LLM.

## Принципы

Dependency inversion: `domain` ← `service`/`service.ports` ← `adapters`; `service` не знает об адаптерах. Импорты — только с границ пакетов (`from domain import ...`, `from call_analytics.service.ports import ...`). LLM получает не сырой transcript, а синхронизированный диалог с speaker coverage, ASR confidence и SER emotion episodes. Thinking у Qwen не отключается.

## Документы

- Спека: `specs/2026-06-18-call-analytics-pipeline-design.md`
- План реализации: `plans/2026-06-18-call-analytics-pipeline.md`
- Runtime migration spec: `docs/superpowers/specs/2026-06-25-clean-pipeline-runtime-design.md`

## Статус

Runtime слой готов: 65 тестов зелёные, `ruff` + `mypy --strict` чисто. Реальные ML/LLM adapter’ы вынесены из временных scripts в `infra/adapters`. Очередь выбрана RabbitMQ-first; Kafka оставлен как будущий adapter/event-log при необходимости replay/high-throughput analytics. **Вне объёма**: фактические FastAPI routes/UI и Kafka adapter.

## Тулинг

Python 3.12, `uv`, pytest (`asyncio_mode=auto`), ruff (line-length 100), mypy strict. Прогон: `uv run pytest`, `uv run ruff check src tests`, `uv run mypy src`.
