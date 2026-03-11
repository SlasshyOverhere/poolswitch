from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class PoolSwitchError(Exception):
    status_code: int
    response_text: str

    def __str__(self) -> str:
        return f"PoolSwitch proxy returned {self.status_code}: {self.response_text}"


class PoolSwitchClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout, headers=self.headers)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        data: Any | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = self._client.request(method=method, url=path, json=json_body, data=data, headers=headers, params=params)
        if response.status_code < 200 or response.status_code >= 300:
            raise PoolSwitchError(status_code=response.status_code, response_text=response.text)
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, *, json: Any | None = None, data: Any | None = None, **kwargs: Any) -> Any:
        return self.request("POST", path, json_body=json, data=data, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoolSwitchClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()



