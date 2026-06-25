# MFC Voice Summer

Пайплайн анализа WAV-записей звонков МФЦ в clean architecture стиле.

## Runtime Model

Запуск разделён на независимые процессы:

- persistent ML services в Docker: ASR, diarization, emotion recognition;
- persistent LLM service vLLM/Qwen, доступный по OpenAI-compatible API;
- RabbitMQ как command queue для обработки записей;
- Python worker/application layer в `src/call_analytics`, который не стартует и не останавливает ML/LLM.

Основной composition root: `call_analytics.bootstrap.build_application()`.
Эта точка сборки предназначена для CLI, worker и будущего FastAPI lifespan.

## Architecture

- `src/domain` - доменные dataclass-модели без infrastructure dependencies.
- `src/call_analytics/service` - use cases: pipeline, dialogue assembly, processing worker.
- `src/call_analytics/infra/ports` - абстрактные порты.
- `src/call_analytics/infra/adapters` - local, in-memory, model API, RabbitMQ и PDF adapters.
- `docker/voice-model-api` - Docker runtime для ASR/diarization/SER model API.

LLM report generator получает не сырой transcript, а синхронизированный диалог:
word timestamps, speaker coverage, ASR confidence и SER emotion episodes. Thinking у Qwen не отключается.

## Local Inputs And Outputs

По умолчанию:

- input recordings: `.recordings/*.wav`
- artifacts/reports: `.reports/`

Финальные PDF/JSON отчёты привязаны к stem исходного WAV-файла.

## Docker Services

```bash
docker compose -f docker-compose.voice.yml up -d rabbitmq asr-api diarization-api emotion-api
```

Compose использует `.recordings` как read-only mount `/data/recordings` внутри model API контейнеров.
Кэш моделей хранится в `model-cache/` и не коммитится.

Qwen/vLLM поднимается отдельно как OpenAI-compatible endpoint. URL задаётся через
`VOICE_QWEN_BASE_URL`, модель через `VOICE_QWEN_MODEL`.

## Environment

Основные переменные:

```bash
VOICE_RECORDINGS_DIR=.recordings
VOICE_ARTIFACTS_DIR=.reports
VOICE_ASR_URL=http://127.0.0.1:8101
VOICE_DIARIZATION_URL=http://127.0.0.1:8102
VOICE_EMOTION_URL=http://127.0.0.1:8103
VOICE_QWEN_BASE_URL=http://127.0.0.1:8000/v1
VOICE_QWEN_MODEL=qwen3.6-35b
VOICE_CONTAINER_RECORDINGS_DIR=/data/recordings
VOICE_RABBITMQ_URL=amqp://guest:guest@localhost/
VOICE_RABBITMQ_QUEUE=voice.recordings
```

Provider tokens, including `HF_TOKEN`, belong in local `.env`. `.env` is ignored by git.

## Verification

```bash
pytest -q
ruff check .
mypy src
```
