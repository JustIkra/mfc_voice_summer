from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import ssl
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Protocol, cast

from call_analytics.infra.adapters.grandstream.cdr import parse_accounts, parse_cdr_page
from call_analytics.service.ports import TelephonyAccount, TelephonyGateway
from domain import DiscoveredCall, Period

LOGGER = logging.getLogger(__name__)
MSK = timezone(timedelta(hours=3))
_AUTH_STATUSES = frozenset({-5, -6})
_CDR_PAGE_SIZE = 1000
_MAX_CDR_PAGES = 100


@dataclass(frozen=True, slots=True)
class GrandstreamHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class GrandstreamTransport(Protocol):
    async def post(
        self,
        payload: dict[str, object],
        timeout: int,
    ) -> GrandstreamHttpResponse: ...


class GrandstreamError(RuntimeError):
    def __init__(self, status: int | None, message: str) -> None:
        self.status = status
        super().__init__(message)


class UrllibGrandstreamTransport:
    def __init__(self, url: str, ca_file: Path) -> None:
        self._url = url
        self._ca_file = ca_file
        self._ssl_context: ssl.SSLContext | None = None

    async def post(
        self,
        payload: dict[str, object],
        timeout: int,
    ) -> GrandstreamHttpResponse:
        return await asyncio.to_thread(self._post, payload, timeout)

    def _post(self, payload: dict[str, object], timeout: int) -> GrandstreamHttpResponse:
        if self._ssl_context is None:
            self._ssl_context = ssl.create_default_context(cafile=str(self._ca_file))
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        request = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
                context=self._ssl_context,
            ) as response:
                return GrandstreamHttpResponse(
                    status_code=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                )
        except urllib.error.HTTPError as error:
            return GrandstreamHttpResponse(
                status_code=error.code,
                headers={key.lower(): value for key, value in error.headers.items()},
                body=error.read(),
            )
        except (TimeoutError, urllib.error.URLError) as error:
            raise GrandstreamError(None, "Grandstream transport request failed") from error


class GrandstreamClient(TelephonyGateway):
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        queue_extension: str,
        queue_name: str,
        ca_file: Path,
        transport: GrandstreamTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        api_timeout_seconds: int = 120,
        download_timeout_seconds: int = 900,
    ) -> None:
        self._username = username
        self._password = password
        self._queue_extension = queue_extension
        self._queue_name = queue_name
        self._transport = transport or UrllibGrandstreamTransport(base_url, ca_file)
        self._sleep = sleep
        self._api_timeout_seconds = api_timeout_seconds
        self._download_timeout_seconds = download_timeout_seconds
        self._cookie: str | None = None

    async def list_accounts(self) -> Sequence[TelephonyAccount]:
        payload = await self._request_json("listAccount")
        return parse_accounts(payload)

    async def list_calls(
        self,
        period: Period,
        accounts: Sequence[TelephonyAccount],
    ) -> Sequence[DiscoveredCall]:
        if period.start.utcoffset() is None or period.end.utcoffset() is None:
            raise ValueError("Grandstream CDR period must be timezone-aware")
        offset = 0
        calls: list[DiscoveredCall] = []
        page_signatures: set[tuple[str, ...]] = set()
        for _ in range(_MAX_CDR_PAGES):
            payload = await self._request_json(
                "cdrapi",
                {
                    "format": "json",
                    "startTime": period.start.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S"),
                    "endTime": period.end.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S"),
                    "numRecords": str(_CDR_PAGE_SIZE),
                    "offset": str(offset),
                },
            )
            groups = payload.get("cdr_root", ())
            if not isinstance(groups, Sequence) or isinstance(groups, str | bytes | bytearray):
                break
            if not groups:
                break
            signature = tuple(
                str(group.get("cdr", "")) for group in groups if isinstance(group, Mapping)
            )
            if signature and signature in page_signatures:
                break
            page_signatures.add(signature)
            calls.extend(
                parse_cdr_page(
                    payload,
                    self._queue_extension,
                    accounts,
                    self._queue_name,
                )
            )
            offset += _CDR_PAGE_SIZE
        else:
            raise GrandstreamError(None, "Grandstream CDR pagination exceeded safety limit")
        return calls

    async def recording_files(self, acct_id: str) -> tuple[str, ...]:
        payload = await self._request_json("getRecordInfosByCall", {"id": acct_id})
        response = payload.get("response")
        if not isinstance(response, Mapping):
            return ()
        value = str(response.get("recordfiles", ""))
        return tuple(item.strip() for item in value.split(",") if item.strip())

    async def download_recording(self, filename: str) -> bytes:
        basename = PurePosixPath(filename.rstrip("@")).name
        response = await self._request(
            "recapi",
            {"filedir": "queue", "filename": basename},
            timeout=self._download_timeout_seconds,
        )
        if _maybe_json(response.body) is not None:
            raise GrandstreamError(None, "Grandstream recording response is not binary")
        return response.body

    async def close(self) -> None:
        cookie = self._cookie
        self._cookie = None
        if cookie is None:
            return
        response = await self._transport.post(
            {"request": {"action": "logout", "cookie": cookie}},
            self._api_timeout_seconds,
        )
        payload = _decode_json(response.body)
        _raise_for_status("logout", payload)
        LOGGER.info("Grandstream action=%s status=%s", "logout", _status(payload))

    async def _request_json(
        self,
        action: str,
        parameters: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        response = await self._request(action, parameters)
        return _decode_json(response.body)

    async def _request(
        self,
        action: str,
        parameters: Mapping[str, object] | None = None,
        *,
        timeout: int | None = None,
        retry_auth: bool = True,
        retry_rate: bool = True,
    ) -> GrandstreamHttpResponse:
        await self._ensure_login()
        request: dict[str, object] = {
            "action": action,
            "cookie": cast(str, self._cookie),
        }
        if parameters:
            request.update(parameters)
        response = await self._transport.post(
            {"request": request},
            timeout or self._api_timeout_seconds,
        )
        payload = _maybe_json(response.body)
        status = _status(payload)
        LOGGER.info("Grandstream action=%s status=%s", action, status)
        if status in _AUTH_STATUSES and retry_auth:
            self._cookie = None
            return await self._request(
                action,
                parameters,
                timeout=timeout,
                retry_auth=False,
                retry_rate=retry_rate,
            )
        if status == -45 and retry_rate:
            await self._sleep(15.0)
            return await self._request(
                action,
                parameters,
                timeout=timeout,
                retry_auth=retry_auth,
                retry_rate=False,
            )
        _raise_for_status(action, payload)
        if response.status_code >= 400:
            raise GrandstreamError(response.status_code, f"Grandstream {action} HTTP error")
        return response

    async def _ensure_login(self) -> None:
        if self._cookie is not None:
            return
        challenge_response = await self._transport.post(
            {
                "request": {
                    "action": "challenge",
                    "user": self._username,
                    "version": "1.0",
                }
            },
            self._api_timeout_seconds,
        )
        challenge_payload = _decode_json(challenge_response.body)
        _raise_for_status("challenge", challenge_payload)
        challenge_body = challenge_payload.get("response")
        if not isinstance(challenge_body, Mapping) or not challenge_body.get("challenge"):
            raise GrandstreamError(None, "Grandstream challenge response is invalid")
        challenge = str(challenge_body["challenge"])
        token = hashlib.md5((challenge + self._password).encode()).hexdigest()
        login_response = await self._transport.post(
            {
                "request": {
                    "action": "login",
                    "user": self._username,
                    "token": token,
                }
            },
            self._api_timeout_seconds,
        )
        login_payload = _decode_json(login_response.body)
        _raise_for_status("login", login_payload)
        login_body = login_payload.get("response")
        if not isinstance(login_body, Mapping) or not login_body.get("cookie"):
            raise GrandstreamError(None, "Grandstream login response is invalid")
        self._cookie = str(login_body["cookie"])
        LOGGER.info("Grandstream action=%s status=%s", "login", _status(login_payload))


def _decode_json(data: bytes) -> dict[str, object]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GrandstreamError(None, "Grandstream JSON response is invalid") from error
    if not isinstance(value, dict):
        raise GrandstreamError(None, "Grandstream JSON response is not an object")
    return cast(dict[str, object], value)


def _maybe_json(data: bytes) -> dict[str, object] | None:
    stripped = data.lstrip()
    if not stripped.startswith(b"{"):
        return None
    return _decode_json(data)


def _status(payload: Mapping[str, object] | None) -> int:
    if payload is None or "status" not in payload:
        return 0
    try:
        return int(cast(int | str, payload["status"]))
    except (TypeError, ValueError):
        return -1


def _raise_for_status(action: str, payload: Mapping[str, object] | None) -> None:
    status = _status(payload)
    if status != 0:
        raise GrandstreamError(status, f"Grandstream {action} failed with status {status}")


__all__ = [
    "GrandstreamClient",
    "GrandstreamError",
    "GrandstreamHttpResponse",
    "GrandstreamTransport",
    "UrllibGrandstreamTransport",
]
