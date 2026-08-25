from __future__ import annotations

import json
from pathlib import Path

from call_analytics.infra.adapters.grandstream import parse_accounts, parse_cdr_page
from domain import CallerNameSource

FIXTURES = Path("tests/fixtures/grandstream")


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parser_returns_one_main_queue_call_with_answered_operator() -> None:
    accounts = parse_accounts(_fixture("accounts.json"))

    calls = parse_cdr_page(_fixture("cdr-page.json"), "6500", accounts)

    assert len(calls) == 1
    assert calls[0].id.value == "cdr:group-001"
    assert calls[0].source_recording.acct_id == "901"
    assert calls[0].source_recording.filenames == ("2026-08/call.wav",)
    assert calls[0].operator is not None
    assert calls[0].operator.extension == "11198"
    assert calls[0].operator.name == "Оператор 11198"
    assert calls[0].caller.id == "79000000001"
    assert calls[0].caller.name is None
    assert calls[0].caller.name_source is CallerNameSource.UNKNOWN


def test_parser_uses_main_acct_fallback_when_group_id_is_missing() -> None:
    payload = _fixture("cdr-page.json")
    cdr_root = payload["cdr_root"]
    del cdr_root[0]["cdr"]

    call = parse_cdr_page(payload, "6500", parse_accounts(_fixture("accounts.json")))[0]

    assert call.id.value == "acct:800"


def test_parser_uses_textual_caller_name_from_cdr() -> None:
    payload = _fixture("cdr-page.json")
    payload["cdr_root"][0]["main_cdr"]["caller_name"] = "Анна"

    call = parse_cdr_page(payload, "6500", parse_accounts(_fixture("accounts.json")))[0]

    assert call.caller.name == "Анна"
    assert call.caller.name_source is CallerNameSource.CDR
    assert call.caller.name_confidence == 1.0
