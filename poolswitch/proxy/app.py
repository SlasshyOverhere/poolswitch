from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

from poolswitch.config import AppConfig
from poolswitch.core.factory import build_key_pool
from poolswitch.core.key_pool import KeyPool
from poolswitch.core.quota import classify_response
from poolswitch.errors import NoHealthyKeysError
from poolswitch.metrics import Metrics
from poolswitch.models import KeyRecord
from poolswitch.retry import RetryPolicy


LOGGER = logging.getLogger("poolswitch")

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def _connection_header_tokens(request: Request) -> set[str]:
    tokens: set[str] = set()
    connection_value = request.headers.get("connection", "")
    for token in connection_value.split(","):
        cleaned = token.strip().lower()
        if cleaned:
            tokens.add(cleaned)
    return tokens


class AsyncRateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self.requests_per_second = max(requests_per_second, 0.1)
        self.max_requests = max(1, math.ceil(self.requests_per_second))
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            window_start = now - 1.0
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_requests:
                delay = self._timestamps[0] - window_start
                await asyncio.sleep(max(delay, 0.001))
                now = time.monotonic()
                window_start = now - 1.0
                while self._timestamps and self._timestamps[0] < window_start:
                    self._timestamps.popleft()
            self._timestamps.append(time.monotonic())


class ProxyService:
    def __init__(self, config: AppConfig, metrics: Metrics, pool: KeyPool, client: httpx.AsyncClient) -> None:
        self.config = config
        self.metrics = metrics
        self.pool = pool
        self.client = client
        self.retry_policy = RetryPolicy(attempts=config.retry_attempts)
        self.rate_limiter = AsyncRateLimiter(config.rate_limit_per_second)

    async def handle(self, request: Request, path: str) -> Response:
        started = time.perf_counter()
        body = await request.body()
        excluded_keys: set[str] = set()
        attempts = 0
        method = request.method.upper()
        retryable_method = method in {item.upper() for item in self.config.retryable_methods}

        while True:
            attempts += 1
            try:
                key_record = await self.pool.acquire_key(excluded_key_ids=excluded_keys)
            except NoHealthyKeysError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            await self.rate_limiter.acquire()

            try:
                upstream = await self._forward(request, key_record, body, path)
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.TimeoutException) as exc:
                await self.pool.record_transient_error(key_record.definition.id, "network_error")
                excluded_keys.add(key_record.definition.id)
                await self.pool.record_failover(key_record.definition.id)
                self.metrics.failovers_total.labels(reason="network_error").inc()
                decision = self.retry_policy.for_attempt(
                    attempt_number=attempts,
                    retryable=retryable_method,
                    reason="network_error",
                )
                if decision.should_retry:
                    await self.retry_policy.sleep(decision)
                    continue
                raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}") from exc

            should_retry, quota_exceeded, reason = await classify_response(upstream)
            if quota_exceeded:
                await self.pool.mark_key_quota_exhausted(key_record.definition.id, reason)
                excluded_keys.add(key_record.definition.id)
                await self.pool.record_failover(key_record.definition.id)
                self.metrics.failovers_total.labels(reason=reason).inc()
                decision = self.retry_policy.for_attempt(
                    attempt_number=attempts,
                    retryable=retryable_method,
                    reason=reason,
                )
                if decision.should_retry:
                    await self.retry_policy.sleep(decision)
                    continue
                return self._build_response(upstream, method, path, started)

            if should_retry:
                await self.pool.record_transient_error(key_record.definition.id, reason)
                excluded_keys.add(key_record.definition.id)
                await self.pool.record_failover(key_record.definition.id)
                self.metrics.failovers_total.labels(reason=reason).inc()
                decision = self.retry_policy.for_attempt(
                    attempt_number=attempts,
                    retryable=retryable_method,
                    reason=reason,
                )
                if decision.should_retry:
                    await self.retry_policy.sleep(decision)
                    continue
                return self._build_response(upstream, method, path, started)

            remaining_quota = self._extract_remaining_quota(upstream)
            await self.pool.record_success(key_record.definition.id, remaining_quota=remaining_quota)
            return self._build_response(upstream, method, path, started)

    async def _forward(self, request: Request, key_record: KeyRecord, body: bytes, path: str) -> httpx.Response:
        headers = self._outbound_headers(request, key_record)
        url = f"{self.config.upstream_base_url.rstrip('/')}/{path.lstrip('/')}"
        LOGGER.info("proxying %s %s with key=%s", request.method, path, key_record.definition.id)
        return await self.client.request(
            method=request.method,
            url=url,
            params=request.query_params,
            content=body,
            headers=headers,
        )

    def _outbound_headers(self, request: Request, key_record: KeyRecord) -> dict[str, str]:
        dynamic_hop_headers = _connection_header_tokens(request)
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
            and key.lower() not in dynamic_hop_headers
            and key.lower() != self.config.auth_header_name.lower()
        }
        key_value = key_record.definition.value
        if self.config.auth_scheme:
            headers[self.config.auth_header_name] = f"{self.config.auth_scheme} {key_value}"
        else:
            headers[self.config.auth_header_name] = key_value
        headers.setdefault("x-poolswitch-key-id", key_record.definition.id)
        return headers

    def _build_response(self, upstream: httpx.Response, method: str, path: str, started: float) -> Response:
        elapsed = time.perf_counter() - started
        self.metrics.requests_total.labels(method=method, path=f"/{path}", status=str(upstream.status_code)).inc()
        self.metrics.request_latency_seconds.labels(method=method, path=f"/{path}").observe(elapsed)
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=self._response_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )

    @staticmethod
    def _response_headers(headers: httpx.Headers) -> dict[str, str]:
        return {key: value for key, value in headers.items() if key.lower() not in HOP_BY_HOP_HEADERS}

    @staticmethod
    def _extract_remaining_quota(response: httpx.Response) -> int | None:
        for header_name in ("x-ratelimit-remaining", "x-remaining-quota", "x-usage-remaining"):
            header_value = response.headers.get(header_name)
            if header_value is None:
                continue
            try:
                return int(float(header_value))
            except ValueError:
                continue

        try:
            payload: dict[str, Any] = response.json()
        except json.JSONDecodeError:
            return None
        usage = payload.get("usage", {})
        remaining = usage.get("remaining_quota") if isinstance(usage, dict) else None
        if isinstance(remaining, int):
            return remaining
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config: AppConfig = app.state.config
    timeout = httpx.Timeout(timeout=config.request_timeout_seconds, connect=config.connect_timeout_seconds)
    client = httpx.AsyncClient(timeout=timeout)
    metrics = Metrics()
    pool = await build_key_pool(config, metrics)
    app.state.metrics = metrics
    app.state.pool = pool
    app.state.proxy_service = ProxyService(config=config, metrics=metrics, pool=pool, client=client)
    try:
        yield
    finally:
        await client.aclose()


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="PoolSwitch Proxy", lifespan=lifespan)
    app.state.config = config

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "name": "poolswitch",
            "status": "ok",
            "upstream_base_url": config.upstream_base_url,
            "endpoints": {
                "health": "/health",
                "status": "/status",
                "metrics": "/metrics",
            },
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/status")
    async def status() -> dict[str, Any]:
        records = await app.state.pool.list_records(include_cooldown=True)
        return {
            "strategy": config.strategy,
            "storage": config.storage.backend,
            "upstream_base_url": config.upstream_base_url,
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

    @app.get("/metrics")
    async def metrics() -> Response:
        body, content_type = app.state.metrics.render()
        return Response(content=body, media_type=content_type)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def proxy(path: str, request: Request) -> Response:
        if path in {"", "health", "healthz", "metrics", "status", "favicon.ico"}:
            raise HTTPException(status_code=404, detail="Route handled internally.")
        return await app.state.proxy_service.handle(request, path)

    return app


