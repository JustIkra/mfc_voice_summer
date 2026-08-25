# MFC Voice Summer

Внутренний дэшборд качества звонков очереди Grandstream UCM `6500 / Call_center`.

Система ежедневно читает CDR за последние 30 дней, скачивает только новые непустые записи, выполняет ASR/diarization/emotion/Qwen-анализ и бессрочно сохраняет итоговый отчёт с полной расшифровкой. Нормализованная запись архивируется в Ogg/Opus на отдельном диске и доступна для прослушивания только внутри открытого отчёта. Исходные части и промежуточные файлы удаляются после обработки.

## Runtime

```text
Grandstream UCM → grandstream-sync → Opus archive
                           ├───────→ SQLite → RabbitMQ → worker
                           │                    ↘ ASR / diarization / emotion / Qwen
Opus archive + SQLite → FastAPI → внутренний dashboard / playback / on-demand PDF
```

- `proxy` — единственный опубликованный HTTP-порт.
- `web` — FastAPI dashboard API и статический frontend.
- `grandstream-sync` — ежедневный 30-дневный sync; по умолчанию выключен до live-smoke.
- `worker` — последовательная обработка jobs из RabbitMQ.
- `rabbitmq` — command queue.
- `asr-api`, `diarization-api`, `emotion-api` — постоянные model services.
- `qwen-api` — OpenAI-compatible vLLM runtime, опциональный Compose profile.

## Хранение

- `.data/call-analytics.sqlite3` — звонки, jobs, sync runs и сжатые финальные отчёты.
- `.data/backups/call-analytics.before-migration.sqlite3` — одна backup-копия перед миграцией существующей схемы.
- `.staging/jobs/<sha256>/` — временный source/model workspace; очищается после success, failure, skip, cancel и crash recovery.
- `/var/recordings-voice-summer/<shard>/<sha256>.ogg` — бессрочный архив Ogg/Opus, mono, 24 kbit/s. Автоматического удаления нет.

Отдельные transcript, diarization, emotion и PDF artifacts не сохраняются. PDF формируется в памяти по HTTP-запросу. `grandstream-sync` монтирует архив read-write, `web` — read-only, worker не имеет доступа к архивному диску.

## Конфигурация

```bash
cp .env.example .env
chmod 600 .env
```

Ключевые переменные:

```text
VOICE_DB_PATH=.data/call-analytics.sqlite3
VOICE_STAGING_DIR=.staging
VOICE_GRANDSTREAM_URL=https://grandstream253.mfcl.mfclnr.ru/api
VOICE_GRANDSTREAM_USER=ranhigs
VOICE_GRANDSTREAM_PASSWORD=
VOICE_GRANDSTREAM_QUEUE=6500
VOICE_GRANDSTREAM_CA_FILE=/usr/local/share/ca-certificates/mfcRootCA.crt
VOICE_SYNC_TIME=02:00
VOICE_SYNC_BATCH_LIMIT=3000
VOICE_SYNC_ENABLED=no
VOICE_SYNC_RUN_ON_START=no
VOICE_ARCHIVE_DIR=/data/recordings
VOICE_ARCHIVE_BITRATE=24k
VOICE_ARCHIVE_RESERVE_BYTES=2147483648
```

Пароль Grandstream хранится только в `.env`, который не коммитится. Cookie, challenge и MD5 token существуют только в памяти API lifecycle. Логи не содержат Caller ID, имена, filenames, transcript или report payload.

## Запуск

```bash
docker compose -f docker-compose.voice.yml -f docker-compose.prod.yml up -d --build
```

Dashboard: `http://<internal-host>:${VOICE_HTTP_PORT:-8080}/`.

Проверка без загрузки записи:

```bash
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/api/sync/status
```

One-shot sync запускается только после явного разрешения на первый `recapi` download:

```bash
docker compose -f docker-compose.voice.yml -f docker-compose.prod.yml run --rm \
  grandstream-sync python -m call_analytics.sync_app --once --limit 1
```

После live-smoke установить `VOICE_SYNC_ENABLED=yes` и перезапустить `grandstream-sync`. Один запуск добавляет не более `VOICE_SYNC_BATCH_LIMIT` новых звонков; дубликаты в лимит не входят.

Backfill архивных записей для уже готовых отчётов запускается newest-first и не повторяет ML-анализ:

```bash
docker compose -f docker-compose.voice.yml -f docker-compose.prod.yml exec \
  grandstream-sync python -m call_analytics.sync_app --backfill-audio --limit 250
```

Повторный backfill пропускает уже существующие файлы. При заполнении диска записи не удаляются: `/api/sync/status` показывает `ok`, `warning`, `critical` или `full`; ниже резерва 2 GiB новая архивация останавливается с явной ошибкой.

На `ranghigs` privileged Docker-команды выполняются через `pamsu`, не `sudo`.

## Web API

```text
GET /health
GET /api/dashboard/summary
GET /api/operators
GET /api/calls
GET /api/calls/{call_id}/audio
GET /api/calls/{call_id}/report
GET /api/calls/{call_id}/report.pdf
GET /api/sync/status
```

Upload, report deletion и manual job endpoints отсутствуют. Audio endpoint работает только для звонка с готовым отчётом и поддерживает HTTP Range для перемотки.

## Разработка

Python 3.12 и locked `uv` environment:

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
docker compose -f docker-compose.voice.yml -f docker-compose.prod.yml config --quiet
```

Архитектурные слои: `domain` ← `call_analytics.service`/`service.ports` ← `infra.adapters`.
