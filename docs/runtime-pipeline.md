# Runtime Pipeline

## Source and synchronization

`grandstream-sync` работает непосредственно на `ranghigs`, где доступен `https://grandstream253.mfcl.mfclnr.ru/api`.

Каждый запуск:

1. получает challenge и выполняет login с API version `1.0`;
2. читает `listAccount`;
3. постранично читает CDR за `[now-30 days, now]` в Europe/Moscow;
4. локально оставляет только `QUEUE[6500]`;
5. разрешает ответившего оператора через `dstanswer → listAccount.extension`;
6. пропускает уже зарегистрированный `call_id`;
7. получает filenames через `getRecordInfosByCall` и временно скачивает `recapi`;
8. валидирует/нормализует запись и публикует job в RabbitMQ;
9. завершает logout и очищает cookie/token из памяти.

`6501 / Call_Center_Reserve` не ingest-ится. Пустые, повреждённые и безречевые вызовы получают `skipped_empty` и не входят в аналитику.

## Processing

Worker выполняет:

```text
TRANSCRIBE → DIARIZE → EMOTION → REPORT
```

Model services являются долгоживущими HTTP-процессами. Pipeline не управляет их lifecycle.

Рабочие данные находятся только в `.staging/jobs/<sha256>/`. При success/failure/skip/cancel каталог удаляется. После crash interrupted job сбрасывает completed stages, очищает workspace и начинает с TRANSCRIBE.

## Persistence

SQLite работает в WAL-режиме с foreign keys и busy timeout:

- `calls` — source snapshot и job state;
- `reports` — индексируемые поля и zlib-compressed canonical report payload;
- `sync_runs` — lifecycle и безопасные счётчики синхронизации.

Final report и `done` job status сохраняются одной транзакцией. Payload включает operator ID/extension/name, Caller ID/name, анализ и полную расшифровку. Звуковые пути и URL отсутствуют.

## Dashboard

FastAPI выполняет server-side aggregation, operator filters, text search и pagination. Только `calls.status='done'` участвует в пользовательских показателях.

Frontend получает summary, operators, calls и sync status через HTTP. Detail dialog загружает canonical payload; PDF строится в памяти. Публичного audio/upload/mutation API нет.

## Failures

- API `-45`: одна пауза 15 секунд и один повтор.
- Истёкшая auth session: одна повторная challenge/login попытка.
- Authentication/permission error: sync останавливается без бесконечных login attempts.
- Retryable processing error: повтор до пяти попыток последующими sync runs.
- Missing operator: terminal failed call, скрытый из аналитики.
- Empty/corrupt/no-speech: terminal `skipped_empty`.

Логи содержат только technical call ID, status и error kind.
