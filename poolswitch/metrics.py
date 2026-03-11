from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests_total = Counter(
            "poolswitch_requests_total",
            "Total proxied requests.",
            ["method", "path", "status"],
            registry=self.registry,
        )
        self.failovers_total = Counter(
            "poolswitch_failovers_total",
            "Number of times a request was retried with a different key.",
            ["reason"],
            registry=self.registry,
        )
        self.key_usage_total = Counter(
            "poolswitch_key_usage_total",
            "Number of requests sent with each key.",
            ["key_id"],
            registry=self.registry,
        )
        self.key_errors_total = Counter(
            "poolswitch_key_errors_total",
            "Errors observed per key.",
            ["key_id", "reason"],
            registry=self.registry,
        )
        self.request_latency_seconds = Histogram(
            "poolswitch_request_latency_seconds",
            "End-to-end proxy latency.",
            ["method", "path"],
            registry=self.registry,
        )
        self.key_cooldown = Gauge(
            "poolswitch_key_cooldown_active",
            "Whether a key is currently in cooldown.",
            ["key_id"],
            registry=self.registry,
        )

    def render(self) -> tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST

