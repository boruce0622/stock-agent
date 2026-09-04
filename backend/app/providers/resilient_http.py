from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

import httpx

MIN_REQUEST_INTERVAL_SECONDS = 1.2
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_RETRIES = 2

_host_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
_host_last_request: dict[str, float] = {}


class ResilientHttpClient:
    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        min_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.min_interval_seconds = min_interval_seconds

    async def get_bytes(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        return await asyncio.to_thread(self._get_bytes_sync, url, params, headers)

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        content = await self.get_bytes(url, params=params, headers=headers)
        try:
            return httpx.Response(200, content=content).json()
        except ValueError as exc:
            raise ValueError("上游接口返回了无效 JSON") from exc

    def _get_bytes_sync(
        self,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> bytes:
        host = urlparse(url).hostname
        if not host:
            raise ValueError("行情接口 URL 缺少域名")
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(min(0.5 * (2 ** (attempt - 1)), 2.0))
            try:
                with _host_locks[host]:
                    remaining = self.min_interval_seconds - (
                        time.monotonic() - _host_last_request.get(host, 0.0)
                    )
                    if remaining > 0:
                        time.sleep(remaining)
                    _host_last_request[host] = time.monotonic()
                    response = httpx.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.timeout_seconds,
                        follow_redirects=True,
                    )
                response.raise_for_status()
                return response.content
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
        raise RuntimeError(f"请求 {host} 失败（已重试 {self.retries} 次）：{last_error}")
