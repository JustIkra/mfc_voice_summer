from __future__ import annotations

import logging

import pytest

from tests.call_analytics.infra.adapters.test_grandstream_client import (
    FakeGrandstreamTransport,
    _client,
)

pytestmark = pytest.mark.asyncio


async def test_client_logs_do_not_contain_authentication_material(caplog) -> None:
    transport = FakeGrandstreamTransport(
        {"listAccount": [{"response": {"account": []}, "status": 0}]}
    )
    caplog.set_level(logging.INFO)

    client = _client(transport)
    await client.list_accounts()
    await client.close()

    output = caplog.text
    for secret in (
        "secret",
        "sid-test",
        "1234567890123456",
        transport.login_token,
    ):
        assert secret is not None
        assert secret not in output
