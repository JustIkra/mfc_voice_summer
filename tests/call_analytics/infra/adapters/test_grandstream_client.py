from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from call_analytics.infra.adapters.grandstream import (
    GrandstreamClient,
    GrandstreamHttpResponse,
)
from call_analytics.service.ports import TelephonyAccount
from domain import Period

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))


class FakeGrandstreamTransport:
    def __init__(self, action_responses: Mapping[str, list[object]] | None = None) -> None:
        self.actions: list[str] = []
        self.requests: list[dict[str, Any]] = []
        self.login_token: str | None = None
        self._responses = {key: list(value) for key, value in (action_responses or {}).items()}

    async def post(self, payload: dict[str, object], timeout: int) -> GrandstreamHttpResponse:
        del timeout
        request = dict(payload["request"])
        action = str(request["action"])
        self.actions.append(action)
        self.requests.append(request)
        if action == "challenge":
            return _json_response({"response": {"challenge": "1234567890123456"}, "status": 0})
        if action == "login":
            self.login_token = str(request["token"])
            return _json_response({"response": {"cookie": "sid-test"}, "status": 0})
        if action == "logout":
            return _json_response({"status": 0})
        values = self._responses.get(action)
        value = values.pop(0) if values else {"status": 0, "response": {}}
        if isinstance(value, bytes):
            return GrandstreamHttpResponse(
                status_code=200,
                headers={"content-type": "application/octet-stream"},
                body=value,
            )
        return _json_response(value)


def _json_response(payload: object) -> GrandstreamHttpResponse:
    return GrandstreamHttpResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode(),
    )


def _client(transport, sleep=None) -> GrandstreamClient:
    async def no_sleep(seconds: float) -> None:
        del seconds

    return GrandstreamClient(
        base_url="https://ucm.example/api",
        username="api-user",
        password="secret",
        queue_extension="6500",
        queue_name="Call_center",
        ca_file=Path("ca.crt"),
        transport=transport,
        sleep=sleep or no_sleep,
    )


async def test_client_uses_challenge_md5_login_and_logout() -> None:
    transport = FakeGrandstreamTransport(
        {
            "listAccount": [
                {
                    "response": {
                        "account": [{"id": 14, "extension": "11198", "fullname": "Оператор"}]
                    },
                    "status": 0,
                }
            ]
        }
    )
    client = _client(transport)

    accounts = await client.list_accounts()
    await client.close()

    assert transport.actions == ["challenge", "login", "listAccount", "logout"]
    assert transport.requests[0]["version"] == "1.0"
    assert transport.login_token == hashlib.md5(b"1234567890123456secret").hexdigest()
    assert transport.requests[2]["cookie"] == "sid-test"
    assert accounts == (TelephonyAccount(id=14, extension="11198", fullname="Оператор"),)


async def test_client_waits_fifteen_seconds_after_minus_45() -> None:
    transport = FakeGrandstreamTransport(
        {
            "listAccount": [
                {"response": {"error_msg": "retry"}, "status": -45},
                {"response": {"account": []}, "status": 0},
            ]
        }
    )
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    await _client(transport, sleep=sleep).list_accounts()

    assert sleeps == [15.0]
    assert transport.actions.count("listAccount") == 2


async def test_client_lists_only_queue_6500_calls_and_uses_local_time() -> None:
    cdr_payload = json.loads(
        Path("tests/fixtures/grandstream/cdr-page.json").read_text(encoding="utf-8")
    )
    transport = FakeGrandstreamTransport({"cdrapi": [cdr_payload]})
    client = _client(transport)
    period = Period(
        start=datetime(2026, 8, 1, tzinfo=MSK),
        end=datetime(2026, 8, 22, 12, 0, tzinfo=MSK),
    )

    calls = await client.list_calls(
        period,
        [TelephonyAccount(id=14, extension="11198", fullname="Оператор 11198")],
    )

    request = next(item for item in transport.requests if item["action"] == "cdrapi")
    assert [call.id.value for call in calls] == ["cdr:group-001"]
    assert request["startTime"] == "2026-08-01T00:00:00"
    assert request["endTime"] == "2026-08-22T12:00:00"
    assert request["numRecords"] == "1000"
    assert request["offset"] == "0"
    assert "caller" not in request


async def test_client_pages_cdr_by_raw_record_offset_until_empty_page() -> None:
    first = json.loads(Path("tests/fixtures/grandstream/cdr-page.json").read_text())
    second = json.loads(Path("tests/fixtures/grandstream/cdr-page.json").read_text())
    second["cdr_root"][0]["cdr"] = "group-002"
    transport = FakeGrandstreamTransport({"cdrapi": [first, second, {"cdr_root": [], "status": 0}]})
    client = _client(transport)
    period = Period(
        start=datetime(2026, 6, 1, tzinfo=MSK),
        end=datetime(2026, 8, 22, 12, 0, tzinfo=MSK),
    )

    calls = await client.list_calls(
        period,
        [TelephonyAccount(id=14, extension="11198", fullname="Оператор 11198")],
    )

    requests = [item for item in transport.requests if item["action"] == "cdrapi"]
    assert [call.id.value for call in calls] == ["cdr:group-001", "cdr:group-002"]
    assert [request["offset"] for request in requests] == ["0", "1000", "2000"]


async def test_client_stops_when_ucm_repeats_the_same_cdr_page() -> None:
    page = json.loads(Path("tests/fixtures/grandstream/cdr-page.json").read_text())
    transport = FakeGrandstreamTransport({"cdrapi": [page, page]})
    client = _client(transport)

    calls = await client.list_calls(
        Period(
            start=datetime(2026, 6, 1, tzinfo=MSK),
            end=datetime(2026, 8, 22, 12, 0, tzinfo=MSK),
        ),
        [TelephonyAccount(id=14, extension="11198", fullname="Оператор 11198")],
    )

    requests = [item for item in transport.requests if item["action"] == "cdrapi"]
    assert [call.id.value for call in calls] == ["cdr:group-001"]
    assert [request["offset"] for request in requests] == ["0", "1000"]


async def test_client_reads_recording_names_and_binary() -> None:
    transport = FakeGrandstreamTransport(
        {
            "getRecordInfosByCall": [
                {
                    "response": {"recordfiles": "2026-08/q6500-a.wav,2026-08/q6500-b.wav"},
                    "status": 0,
                }
            ],
            "recapi": [b"RIFFdemo"],
        }
    )
    client = _client(transport)

    filenames = await client.recording_files("901")
    content = await client.download_recording(filenames[0])

    request = next(item for item in transport.requests if item["action"] == "recapi")
    assert filenames == ("2026-08/q6500-a.wav", "2026-08/q6500-b.wav")
    assert request["filedir"] == "queue"
    assert request["filename"] == "q6500-a.wav"
    assert content == b"RIFFdemo"
