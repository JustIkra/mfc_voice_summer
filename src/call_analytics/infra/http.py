from __future__ import annotations

import asyncio
import json
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any, cast

PostJson = Callable[[str, dict[str, Any], int], Awaitable[dict[str, Any]]]


async def urllib_post_json(
    url: str, payload: dict[str, Any], timeout: int
) -> dict[str, Any]:
    def _post() -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": "Bearer EMPTY",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))

    return await asyncio.to_thread(_post)


__all__ = ["PostJson", "urllib_post_json"]
