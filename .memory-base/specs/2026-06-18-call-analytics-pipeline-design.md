# Дизайн: пайплайн анализа звонков ИИ колл-центра (Naumen)

- Дата: 2026-06-18
- Статус: утверждён, готов к плану реализации
- Объём задачи: **скелет** — доменная модель + абстракции инфра-уровня (порты) + сервисы-оркестраторы + noop/in_memory адаптеры для тестов. Реальных адаптеров (Naumen-клиент, faster-whisper, SER, qwen) на этом этапе нет.

## 1. Контекст и задача

ИИ колл-центр на базе Naumen Contact Center. Есть доступ к техдокументации; за 3 месяца известна длительность голосовых записей (сайзинг):

| Месяц | Длительность (чч:мм:сс) |
|---|---|
| Январь | 583:50:38 |
| Февраль | 611:46:30 |
| Март | 619:14:24 |

Итого ≈ 1814 часов за квартал — мотивирует устойчивую к падениям оркестрацию (job со статусами + персист артефактов): прогон whisper долгий, терять его при падении поздней стадии нельзя. В домен длительности не моделируются — это сайзинг-контекст.

### Пайплайн

```
Naumen (WAV/GSM0610)  →  TRANSCRIBE      →  DIARIZE          →  EMOTION              →  REPORT
                          faster-whisper     оператор/клиент      Speech Emotion Recog.   qwen 3.x MoE
                          текст              кто говорит          эмоции по сегментам     удовл./содержание
```

### Факты о Naumen (из публичной документации)

- Записи хранятся в **WAV с компрессией GSM0610**.
- Модуль записи умеет писать **моно и стерео**; в стерео — **голос клиента и оператора в раздельных каналах** (конфигурируется), рассчитано на речевую аналитику.
- Выгрузка — экспорт аудиофайлов (web-плеер / архив записей).
- Источники: [запись разговоров](https://www.naumen.ru/products/phone/blog/zapis-razgovorov-v-naumen-contact-center-kak-dlya-kogo-i-zachem/), [управление записями](https://www.naumen.ru/products/phone/tour/features/managing_talk_records/).

**Следствие:** диаризация — **единый порт** `SpeakerDiarizer`; «моно или стерео» решает адаптер (стерео → разбивка по каналам `оператор=0/клиент=1`; моно → ML-диаризация). Сервис разницы не видит.

## 2. Архитектурные принципы

Ports & adapters / dependency inversion (cosmic python; конвенции референса `Knowleage_base_for_kyrsk`):

- `domain` — чистые `@dataclass(frozen=True, slots=True)`, ноль инфра-зависимостей.
- Порты инфры — `abc.ABC` с `async`-методами; у каждого своя контрактная ошибка `<Port>Error` с вложенным `Kind(Enum)` и фабричными classmethod-ами. Адаптер обязан заворачивать провайдер-специфичные исключения.
- Сервис зависит только от портов и домена → юнит-тесты на фейках, та же бизнес-логика при подмене инфраструктуры.
- Докстринги на русском; комментариев в коде нет.

## 3. Раскладка пакетов и границы модулей

```
src/
  domain/
    __init__.py                 # граница: __all__ публичных моделей
    recording.py  transcript.py  diarization.py  emotion.py  report.py  job.py  errors.py
  call_analytics/
    __init__.py
    infra/
      __init__.py
      ports/
        __init__.py             # __all__: порты + их *Error
        recording_source.py  transcriber.py  diarizer.py  emotion_recognizer.py
        report_generator.py  job_repository.py  artifact_store.py
      adapters/
        __init__.py
        in_memory/__init__.py   # InMemoryJobRepository, InMemoryArtifactStore
        noop/__init__.py        # NoopTranscriber, NoopDiarizer, NoopEmotionRecognizer, NoopReportGenerator
    service/
      __init__.py               # CallProcessingService
      ports/
        __init__.py             # CallProcessingPipeline
        pipeline.py
      pipeline.py
```

### Правила границ (OCP + изоляция)

- Каждый пакет экспортирует публичный контракт через `__all__` в своём `__init__.py`. Потребитель импортирует **только с границы** (`from domain import CallRecording`, `from call_analytics.infra.ports import Transcriber`), не по глубоким путям.
- Расширение системы (новый адаптер/стадия) не меняет публичную поверхность пакета — open/closed.
- Направление зависимостей — внутрь, к домену:
  - `domain` не импортирует ничего из `call_analytics`.
  - `service` зависит только от `infra/ports` и `domain` (не от `adapters`).
  - `adapters` зависят от `ports` + внешних либ.

## 4. Доменная модель

- **`RecordingId`** — value object (обёртка над str).
- **`ChannelLayout`** — `MONO | STEREO`.
- **`AudioBlob`** — `data: bytes`, `codec: str`, `layout: ChannelLayout`. Сырое аудио, тянется через порт.
- **`CallRecording`** — `id: RecordingId`, `started_at: datetime` (MSK-aware), `duration: timedelta`, `channel_layout`, `operator_id: str | None`, `metadata: Mapping`.
- **`TimeSpan`** — `start: timedelta`, `end: timedelta` (оффсеты внутри звонка).
- **`TranscriptSegment`** — `span: TimeSpan`, `text: str`, `channel: int | None`, `confidence: float`.
- **`Transcript`** — `recording_id`, `language: str`, `segments: tuple[TranscriptSegment, ...]`, `full_text: str`.
- **`SpeakerRole`** — `OPERATOR | CLIENT | UNKNOWN`.
- **`DiarizedSegment`** — `span: TimeSpan`, `role: SpeakerRole`, `text: str`.
- **`DiarizedTranscript`** — `recording_id`, `segments: tuple[DiarizedSegment, ...]`.
- **`EmotionLabel`** — набор классов SER (`NEUTRAL | HAPPY | ANGRY | SAD | FEARFUL | ...`).
- **`SegmentEmotion`** — `span`, `role`, `label: EmotionLabel`, `scores: Mapping[EmotionLabel, float]`.
- **`EmotionAnalysis`** — `recording_id`, `segments: tuple[SegmentEmotion, ...]`.
- **`Satisfaction`** — `SATISFIED | NEUTRAL | DISSATISFIED`.
- **`CallReport`** — `recording_id`, `satisfaction: Satisfaction`, `summary: str` (содержание звонка), `key_points: tuple[str, ...]`, `generated_at: datetime`.

### Машина состояний (агрегат)

- **`JobStage`** — `TRANSCRIBE → DIARIZE → EMOTION → REPORT` (упорядочены).
- **`JobStatus`** — `PENDING | RUNNING | DONE | FAILED`.
- **`CallProcessingJob`** — `id`, `recording_id`, `completed_stages: frozenset[JobStage]`, `status`, `attempts: Mapping[JobStage, int]`, `last_error: tuple[str, str] | None` (kind, message), `created_at`. (Поле `updated_at` намеренно опущено в скелете: чтобы не тащить `now()` в каждый доменный переход; добавим, когда появится консьюмер времени обновления.)
  - Методы-переходы: `start_stage(stage)`, `complete_stage(stage)`, `fail_stage(stage, kind, message)`, `retry()`. Невалидный переход → `InvalidJobTransition`.
  - `next_stage() -> JobStage | None` — первая незавершённая стадия в порядке.
- **`InvalidJobTransition`** (`domain/errors.py`) — доменная ошибка.

## 5. Инфра-порты

Каждый: `abc.ABC`, `async`-методы, контрактная ошибка `<Port>Error(Kind)` с фабричными методами.

| Порт | Методы | Назначение / `Kind` |
|---|---|---|
| `CallRecordingSource` | `list_recordings(period) -> Sequence[CallRecording]`; `fetch_audio(id) -> AudioBlob` | Naumen-экспорт. `Kind`: CONNECTION, TIMEOUT, NOT_FOUND, AUTH, UNEXPECTED |
| `Transcriber` | `transcribe(audio: AudioBlob) -> Transcript` | faster-whisper. `Kind`: CONNECTION, TIMEOUT, INVALID_FORMAT, UNEXPECTED |
| `SpeakerDiarizer` | `diarize(audio, transcript) -> DiarizedTranscript` | mono/stereo решает адаптер |
| `EmotionRecognizer` | `recognize(audio, diarized) -> EmotionAnalysis` | SER |
| `ReportGenerator` | `generate(diarized, emotions) -> CallReport` | qwen. `Kind`: CONNECTION, TIMEOUT, RATE_LIMIT, INVALID_REQUEST, SERVER, UNEXPECTED |
| `JobRepository` | `save(job)`; `get(id) -> CallProcessingJob \| None`; `list_by_status(status) -> Sequence[...]` | Персист машины состояний |
| `ArtifactStore` | `save_transcript/diarization/emotion/report`; `load_transcript/diarization/emotion/report` | Выходы стадий → идемпотентный ретрай без пересчёта |

`Kind` делит ошибки на **retryable** (CONNECTION, TIMEOUT, RATE_LIMIT, SERVER) и **terminal** (INVALID_FORMAT, UNSUPPORTED, AUTH, INVALID_REQUEST).

## 6. Сервис-оркестратор

`service/ports/pipeline.py` — `CallProcessingPipeline` (интерфейс use-case).
`service/pipeline.py` — `CallProcessingService(CallProcessingPipeline)`, зависит только от портов:

- `enqueue(recording) -> CallProcessingJob` — создаёт job в PENDING.
- `run_next_stage(job_id) -> CallProcessingJob` — выполняет `job.next_stage()`: читает вход (`ArtifactStore` или `fetch_audio`), вызывает compute-порт, сохраняет выход в `ArtifactStore`, двигает job доменным переходом, персистит. Если стадия в `completed_stages` — пропускает (идемпотентность).
- `process(recording_id) -> CallProcessingJob` — гоняет `run_next_stage` до REPORTED/FAILED.
- `retry(job_id) -> CallProcessingJob` — сбрасывает упавшую стадию в PENDING; готовые артефакты сохраняются.

Маппинг стадий: TRANSCRIBE (`audio→Transcript`) → DIARIZE (`audio+Transcript→DiarizedTranscript`) → EMOTION (`audio+Diarized→EmotionAnalysis`) → REPORT (`Diarized+Emotion→CallReport`).

## 7. Обработка ошибок

- Compute-порт падает → сервис ловит `<Port>Error` → `job.fail_stage(stage, kind, msg)` → персист → остановка пайплайна. По `Kind` внешний планировщик решает ретрай (retryable vs terminal).
- Невалидные переходы стадий → `InvalidJobTransition`.

## 8. Тестирование

- `noop`-адаптеры (детерминированные `Transcript`/`DiarizedTranscript`/`EmotionAnalysis`/`CallReport`) + `in_memory` репозитории реализуют те же порты.
- Юнит-тесты:
  - переходы машины состояний (валидные/невалидные, `next_stage`);
  - оркестрация на фейках (полный прогон до REPORT);
  - идемпотентность `run_next_stage` (повтор завершённой стадии — no-op);
  - ретрай пересчитывает **только** упавшую стадию, ранее посчитанные артефакты не теряются.
- Реального ML в тестах нет — меняется только инфраструктура (cosmic python).

## 9. Вне объёма (YAGNI)

- Реальные адаптеры (Naumen-клиент, faster-whisper, SER, qwen) — отдельный цикл.
- Внешний планировщик/очередь, ретрай-политики, БД-схемы, web-API, агрегатная аналитика по длительностям/удовлетворённости.
