# MFC Voice Summer

Внутренний дэшборд качества звонков очереди Grandstream UCM `6500 / Call_center`.

Система ежедневно читает CDR за последние 30 дней, скачивает только новые непустые записи, выполняет ASR/diarization/emotion/Qwen-анализ и бессрочно сохраняет итоговый отчёт с полной расшифровкой. Исходные и промежуточные звуковые файлы удаляются после каждого терминального результата и не выдаются через web.

## Runtime

```text
Grandstream UCM → grandstream-sync → SQLite → RabbitMQ → worker
                                             ↘ ASR / diarization / emotion / Qwen
SQLite → FastAPI → внутренний dashboard / on-demand PDF
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

Отдельные transcript, diarization, emotion, PDF и звуковые artifacts не сохраняются. PDF формируется в памяти по HTTP-запросу.

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
VOICE_SYNC_ENABLED=no
VOICE_SYNC_RUN_ON_START=no
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

После live-smoke установить `VOICE_SYNC_ENABLED=yes` и перезапустить `grandstream-sync`.

На `ranghigs` privileged Docker-команды выполняются через `pamsu`, не `sudo`.

## Web API

```text
GET /health
GET /api/dashboard/summary
GET /api/operators
GET /api/calls
GET /api/calls/{call_id}/report
GET /api/calls/{call_id}/report.pdf
GET /api/sync/status
```

Upload, playback, report deletion и manual job endpoints отсутствуют.

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
