# Обзор проекта: анализ звонков ИИ колл-центра (Naumen)

Скелет clean-architecture (ports & adapters) для пайплайна обработки голосовых записей звонков из Naumen Contact Center:

```
Naumen (WAV/GSM0610) → TRANSCRIBE (whisper) → DIARIZE (оператор/клиент)
                     → EMOTION (SER) → REPORT (qwen: удовлетворённость + содержание)
```

## Слои

- `src/domain/` — чистые `@dataclass(frozen=True, slots=True)`, ноль инфра-зависимостей. Модели звонка/транскрипта/диаризации/эмоций/отчёта + машина состояний `CallProcessingJob` (стадии `TRANSCRIBE→DIARIZE→EMOTION→REPORT`, статусы `PENDING/RUNNING/DONE/FAILED`, ретрай только упавшей стадии). Граница — `domain/__init__.py` (`__all__`).
- `src/call_analytics/infra/ports/` — абстрактные порты (`abc.ABC`) с контрактными ошибками `<Port>Error(Kind)`: `CallRecordingSource`, `Transcriber`, `SpeakerDiarizer` (mono/stereo решает адаптер), `EmotionRecognizer`, `ReportGenerator`, `JobRepository`, `ArtifactStore`.
- `src/call_analytics/infra/adapters/` — `noop/` (детерминированные compute-заглушки), `in_memory/` (репозитории для тестов).
- `src/call_analytics/service/` — `CallProcessingService` оркестрирует стадии поверх портов; идемпотентность + ретрай без пересчёта (артефакты в `ArtifactStore`).

## Принципы

Dependency inversion: `domain` ← `service` ← `adapters`; `service` не знает об адаптерах. Импорты — только с границ пакетов (`from domain import ...`, `from call_analytics.infra.ports import ...`). Докстринги на русском, комментариев в коде нет.

## Документы

- Спека: `specs/2026-06-18-call-analytics-pipeline-design.md`
- План реализации: `plans/2026-06-18-call-analytics-pipeline.md`

## Статус

Скелет готов: 40 тестов зелёные, `ruff` + `mypy --strict` чисто. **Вне объёма** (следующий цикл): реальные адаптеры Naumen/faster-whisper/SER/qwen, планировщик/очередь, БД-персист, web-API.

## Тулинг

Python 3.12, `uv`, pytest (`asyncio_mode=auto`), ruff (line-length 100), mypy strict. Прогон: `uv run pytest`, `uv run ruff check src tests`, `uv run mypy src`.
