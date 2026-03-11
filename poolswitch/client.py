from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from poolswitch.config import AppConfig, KeyConfig, StorageConfig
from poolswitch.core.factory import build_key_pool
from poolswitch.core.quota import classify_response
from poolswitch.errors import NoHealthyKeysError
from poolswitch.metrics import Metrics
from poolswitch.models import APIKeyDefinition
from poolswitch.proxy.app import AsyncRateLimiter, ProxyService
from poolswitch.retry import RetryPolicy


KeyInput = str | KeyConfig | APIKeyDefinition | Mapping[str, Any]
AsyncClientFactory = Callable[[httpx.Timeout], httpx.AsyncClient]


@dataclass(slots=True)
class PoolSwitchError(Exception):
    message: str
    status_code: int | None = None
    response_text: str | None = None
    reason: str = ""
    cause: Exception | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.reason:
            parts.append(f"reason={self.reason}")
        if self.response_text:
            parts.append(self.response_text)
        return ": ".join(parts)


def _coerce_key_config(value: KeyInput, index: int) -> KeyConfig:
    if isinstance(value, KeyConfig):
        return value
    if isinstance(value, APIKeyDefinition):
        return KeyConfig(
            id=value.id,
            value=value.value,
            monthly_quota=value.monthly_quota,
            metadata=value.metadata,
        )
    if isinstance(value, str):
        return KeyConfig(id=f"key-{index}", value=value)
    if isinstance(value, Mapping):
        return KeyConfig.model_validate(value)
    raise TypeError("keys must contain strings, mappings, KeyConfig, or APIKeyDefinition values")


def _coerce_storage_config(storage: StorageConfig | Mapping[str, Any] | None) -> StorageConfig:
    if storage is None:
        return StorageConfig()
    if isinstance(storage, StorageConfig):
        return storage
    return StorageConfig.model_validate(dict(storage))


def _build_client_config(
    *,
    upstream_base_url: str,
    keys: Sequence[KeyInput],
    auth_header_name: str,
    auth_scheme: str | None,
    strategy: str,
    retry_attempts: int,
    cooldown_seconds: int,
    request_timeout_seconds: float,
    connect_timeout_seconds: float,
    rate_limit_per_second: float,
    retryable_methods: Sequence[str] | None,
    storage: StorageConfig | Mapping[str, Any] | None,
) -> AppConfig:
    return AppConfig(
        upstream_base_url=upstream_base_url,
        auth_header_name=auth_header_name,
        auth_scheme=auth_scheme,
        strategy=strategy,
        retry_attempts=retry_attempts,
        cooldown_seconds=cooldown_seconds,
        request_timeout_seconds=request_timeout_seconds,
        connect_timeout_seconds=connect_timeout_seconds,
        rate_limit_per_second=rate_limit_per_second,
        retryable_methods=list(retryable_methods or ["GET", "HEAD", "OPTIONS", "DELETE", "POST"]),
        storage=_coerce_storage_config(storage),
        keys=[_coerce_key_config(value, index=index) for index, value in enumerate(keys, start=1)],
    )


class AsyncPoolSwitchClient:
    def __init__(
        self,
        *,
        upstream_base_url: str,
        keys: Sequence[KeyInput],
        auth_header_name: str = "Authorization",
        auth_scheme: str | None = "Bearer",
        strategy: str = "quota_failover",
        retry_attempts: int = 3,
        cooldown_seconds: int = 3600,
        request_timeout_seconds: float = 60.0,
        connect_timeout_seconds: float = 10.0,
        rate_limit_per_second: float = 50.0,
        retryable_methods: Sequence[str] | None = None,
        storage: StorageConfig | Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        client_factory: AsyncClientFactory | None = None,
        metrics: Metrics | None = None,
    ) -> None:
        self.config = _build_client_config(
            upstream_base_url=upstream_base_url,
            keys=keys,
            auth_header_name=auth_header_name,
            auth_scheme=auth_scheme,
            strategy=strategy,
            retry_attempts=retry_attempts,
            cooldown_seconds=cooldown_seconds,
            request_timeout_seconds=request_timeout_seconds,
            connect_timeout_seconds=connect_timeout_seconds,
            rate_limit_per_second=rate_limit_per_second,
            retryable_methods=retryable_methods,
            storage=storage,
        )
        self.headers = dict(headers or {})
        self.metrics = metrics or Metrics()
        self.retry_policy = RetryPolicy(attempts=self.config.retry_attempts)
        self.rate_limiter = AsyncRateLimiter(self.config.rate_limit_per_second)
        self._client = client
        self._client_factory = client_factory
        self._owns_client = client is None
        self._pool = None
        self._setup_lock = asyncio.Lock()
        self._closed = False

    async def _ensure_ready(self) -> None:
        if self._closed:
            raise RuntimeError("PoolSwitch client is closed")
        if self._pool is not None:
            return
        async with self._setup_lock:
            if self._pool is not None:
                return
            timeout = httpx.Timeout(
                timeout=self.config.request_timeout_seconds,
                connect=self.config.connect_timeout_seconds,
            )
            if self._client is None:
                factory = self._client_factory or (lambda timeout_value: httpx.AsyncClient(timeout=timeout_value))
                self._client = factory(timeout)
            self._pool = await build_key_pool(self.config, self.metrics)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        data: Any | None = None,
        content: Any | None = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        await self._ensure_ready()
        excluded_keys: set[str] = set()
        attempts = 0
        method_upper = method.upper()
        retryable_method = method_upper in {item.upper() for item in self.config.retryable_methods}

        while True:
            attempts += 1
            try:
                key_record = await self._pool.acquire_key(excluded_key_ids=excluded_keys)
            except NoHealthyKeysError as exc:
                raise PoolSwitchError("No healthy API keys available", reason="no_healthy_keys", response_text=str(exc)) from exc

            await self.rate_limiter.acquire()

            try:
                response = await self._client.request(
                    method=method_upper,
                    url=self._resolve_url(path),
                    json=json,
                    data=data,
                    content=content,
                    headers=self._request_headers(headers, key_record.definition),
                    params=params,
                )
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.TimeoutException) as exc:
                await self._pool.record_transient_error(key_record.definition.id, "network_error")
                excluded_keys.add(key_record.definition.id)
                await self._pool.record_failover(key_record.definition.id)
                self.metrics.failovers_total.labels(reason="network_error").inc()
                decision = self.retry_policy.for_attempt(
                    attempt_number=attempts,
                    retryable=retryable_method,
                    reason="network_error",
                )
                if decision.should_retry:
                    await self.retry_policy.sleep(decision)
                    continue
                raise PoolSwitchError(
                    "Upstream request failed",
                    reason="network_error",
                    response_text=str(exc),
                    cause=exc,
                ) from exc

            should_retry, quota_exceeded, reason = await classify_response(response)
            if quota_exceeded:
                await self._pool.mark_key_quota_exhausted(key_record.definition.id, reason)
                excluded_keys.add(key_record.definition.id)
                await self._pool.record_failover(key_record.definition.id)
                self.metrics.failovers_total.labels(reason=reason).inc()
                decision = self.retry_policy.for_attempt(
                    attempt_number=attempts,
                    retryable=retryable_method,
                    reason=reason,
                )
                if decision.should_retry:
                    await self.retry_policy.sleep(decision)
                    continue
                return self._finalize_response(response, reason=reason)

            if should_retry:
                await self._pool.record_transient_error(key_record.definition.id, reason)
                excluded_keys.add(key_record.definition.id)
                await self._pool.record_failover(key_record.definition.id)
                self.metrics.failovers_total.labels(reason=reason).inc()
                decision = self.retry_policy.for_attempt(
                    attempt_number=attempts,
                    retryable=retryable_method,
                    reason=reason,
                )
                if decision.should_retry:
                    await self.retry_policy.sleep(decision)
                    continue
                return self._finalize_response(response, reason=reason)

            remaining_quota = ProxyService._extract_remaining_quota(response)
            await self._pool.record_success(key_record.definition.id, remaining_quota=remaining_quota)
            return self._finalize_response(response)

    def _request_headers(self, headers: Mapping[str, str] | None, definition: APIKeyDefinition) -> dict[str, str]:
        merged: dict[str, str] = {}
        merged.update(self.headers)
        if headers:
            merged.update(headers)
        auth_header = self.config.auth_header_name.lower()
        sanitized = {key: value for key, value in merged.items() if key.lower() != auth_header}
        if self.config.auth_scheme:
            sanitized[self.config.auth_header_name] = f"{self.config.auth_scheme} {definition.value}"
        else:
            sanitized[self.config.auth_header_name] = definition.value
        return sanitized

    def _resolve_url(self, path: str) -> str:
        return f"{self.config.upstream_base_url.rstrip('/')}/{path.lstrip('/')}"

    def _finalize_response(self, response: httpx.Response, *, reason: str = "") -> Any:
        if 200 <= response.status_code < 300:
            return self._parse_response(response)
        raise PoolSwitchError(
            "Upstream returned an error",
            status_code=response.status_code,
            response_text=response.text,
            reason=reason,
        )

    @staticmethod
    def _parse_response(response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            return response.json()
        return response.text

    async def status(self) -> dict[str, Any]:
        await self._ensure_ready()
        records = await self._pool.list_records(include_cooldown=True)
        return {
            "strategy": self.config.strategy,
            "storage": self.config.storage.backend,
            "upstream_base_url": self.config.upstream_base_url,
            "keys": [
                {
                    "id": record.definition.id,
                    "total_requests": record.state.total_requests,
                    "error_count": record.state.error_count,
                    "failover_count": record.state.failover_count,
                    "estimated_remaining_quota": record.state.estimated_remaining_quota,
                    "last_used_at": record.state.last_used_at.isoformat() if record.state.last_used_at else None,
                    "cooldown_until": record.state.cooldown_until.isoformat() if record.state.cooldown_until else None,
                }
                for record in records
            ],
        }

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        if self._pool is not None:
            redis = getattr(self._pool.state_store, "redis", None)
            if redis is not None and hasattr(redis, "aclose"):
                await redis.aclose()

    async def __aenter__(self) -> "AsyncPoolSwitchClient":
        await self._ensure_ready()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> Any:
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> Any:
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self.request("DELETE", path, **kwargs)


class PoolSwitchClient:
    def __init__(self, **kwargs: Any) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="poolswitch-client", daemon=True)
        self._thread.start()
        self._closed = False
        self._client = self._submit(self._create_client(kwargs))

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    async def _create_client(self, kwargs: dict[str, Any]) -> AsyncPoolSwitchClient:
        client = AsyncPoolSwitchClient(**kwargs)
        await client._ensure_ready()
        return client

    def _submit(self, coroutine: Any) -> Any:
        if self._closed:
            raise RuntimeError("PoolSwitch client is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._closed:
            raise RuntimeError("PoolSwitch client is closed")
        return self._submit(self._client.request(method, path, **kwargs))

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    def status(self) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("PoolSwitch client is closed")
        return self._submit(self._client.status())

    def close(self) -> None:
        if self._closed:
            return
        self._submit(self._client.aclose())
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def __enter__(self) -> "PoolSwitchClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
