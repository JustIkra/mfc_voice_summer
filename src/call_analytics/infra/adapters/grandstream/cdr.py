from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from call_analytics.service.ports import TelephonyAccount
from domain import (
    CallerIdentity,
    CallerNameSource,
    DiscoveredCall,
    OperatorIdentity,
    QueueIdentity,
    RecordingId,
    SourceRecordingIdentity,
)

MSK = timezone(timedelta(hours=3))


def parse_accounts(payload: Mapping[str, object]) -> tuple[TelephonyAccount, ...]:
    response = _mapping(payload.get("response"))
    rows = response.get("account", ()) if response else ()
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        return ()
    accounts = []
    for value in rows:
        row = _mapping(value)
        if row is None:
            continue
        extension = _string(row.get("extension"))
        identifier = row.get("id")
        if not extension or identifier is None:
            continue
        fullname = _string(row.get("fullname")) or extension
        try:
            account_id = int(cast(int | str, identifier))
        except (TypeError, ValueError):
            continue
        accounts.append(
            TelephonyAccount(
                id=account_id,
                extension=extension,
                fullname=fullname,
            )
        )
    return tuple(accounts)


def parse_cdr_page(
    payload: Mapping[str, object],
    queue_extension: str,
    accounts: Sequence[TelephonyAccount],
    queue_name: str = "Call_center",
) -> tuple[DiscoveredCall, ...]:
    account_by_extension = {account.extension: account for account in accounts}
    groups = payload.get("cdr_root", ())
    if not isinstance(groups, Sequence) or isinstance(groups, str):
        return ()
    calls = []
    for value in groups:
        group = _mapping(value)
        if group is None:
            continue
        nodes = _cdr_nodes(group)
        if not any(
            _string(node.get("action_type")) == f"QUEUE[{queue_extension}]" for node in nodes
        ):
            continue
        main_nodes = _cdr_nodes(group.get("main_cdr"))
        main = main_nodes[0] if main_nodes else (nodes[0] if nodes else None)
        if main is None:
            continue
        call_id = _call_id(group, main)
        started_at = _parse_datetime(_string(main.get("start")))
        if call_id is None or started_at is None:
            continue
        caller_id = _string(main.get("src")) or None
        caller = _caller(main, caller_id, account_by_extension)
        operator = _operator(nodes, account_by_extension)
        recording_node = _recording_node(nodes)
        source_node = recording_node or main
        filenames = _filenames(source_node.get("recordfiles"))
        calls.append(
            DiscoveredCall(
                id=RecordingId(call_id),
                started_at=started_at,
                duration=timedelta(seconds=_duration(main, nodes)),
                queue=QueueIdentity(extension=queue_extension, name=queue_name),
                caller=caller,
                operator=operator,
                source_recording=SourceRecordingIdentity(
                    acct_id=_string(source_node.get("AcctId")) or None,
                    filenames=filenames,
                ),
            )
        )
    return tuple(calls)


def _cdr_nodes(value: object) -> list[Mapping[str, Any]]:
    nodes: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, Any], value)
        if "start" in mapping and {"src", "dst", "AcctId", "disposition"} & mapping.keys():
            nodes.append(mapping)
        for item in mapping.values():
            nodes.extend(_cdr_nodes(item))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for item in value:
            nodes.extend(_cdr_nodes(item))
    return nodes


def _call_id(group: Mapping[str, Any], main: Mapping[str, Any]) -> str | None:
    group_id = _string(group.get("cdr"))
    if group_id:
        return f"cdr:{group_id}"
    acct_id = _string(main.get("AcctId"))
    return f"acct:{acct_id}" if acct_id else None


def _caller(
    main: Mapping[str, Any],
    caller_id: str | None,
    accounts: Mapping[str, TelephonyAccount],
) -> CallerIdentity:
    cdr_name = _string(main.get("caller_name"))
    if cdr_name and any(character.isalpha() for character in cdr_name):
        return CallerIdentity(
            id=caller_id,
            name=cdr_name,
            name_source=CallerNameSource.CDR,
            name_confidence=1.0,
        )
    account = accounts.get(caller_id or "")
    if account is not None:
        return CallerIdentity(
            id=caller_id,
            name=account.fullname,
            name_source=CallerNameSource.ACCOUNT,
            name_confidence=1.0,
        )
    return CallerIdentity(id=caller_id)


def _operator(
    nodes: Sequence[Mapping[str, Any]],
    accounts: Mapping[str, TelephonyAccount],
) -> OperatorIdentity | None:
    candidates: list[tuple[datetime, TelephonyAccount]] = []
    for node in nodes:
        if _string(node.get("disposition")).upper() != "ANSWERED":
            continue
        account = accounts.get(_string(node.get("dstanswer")))
        answered_at = _parse_datetime(_string(node.get("answer")) or _string(node.get("start")))
        if account is not None and answered_at is not None:
            candidates.append((answered_at, account))
    if not candidates:
        return None
    account = min(candidates, key=lambda item: item[0])[1]
    return OperatorIdentity(
        id=account.id,
        extension=account.extension,
        name=account.fullname,
    )


def _recording_node(nodes: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return next((node for node in nodes if _filenames(node.get("recordfiles"))), None)


def _filenames(value: object) -> tuple[str, ...]:
    return tuple(item.strip() for item in _string(value).split(",") if item.strip())


def _duration(main: Mapping[str, Any], nodes: Sequence[Mapping[str, Any]]) -> float:
    values = [_float(main.get("duration"))]
    values.extend(_float(node.get("duration")) for node in nodes)
    values.extend(_float(node.get("billsec")) for node in nodes)
    return max(values, default=0.0)


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=MSK)
    except ValueError:
        return None


def _float(value: object) -> float:
    try:
        return float(cast(float | int | str, value))
    except (TypeError, ValueError):
        return 0.0


def _mapping(value: object) -> Mapping[str, Any] | None:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else None


def _string(value: object) -> str:
    return str(value).strip() if value is not None else ""


__all__ = ["parse_accounts", "parse_cdr_page"]
