---
title: Metrics and Health
description: Observe PoolSwitch with health checks, status, and Prometheus-compatible metrics.
---

# Metrics and Health

## Health endpoints

PoolSwitch exposes:

- `GET /health`
- `GET /status`
- `GET /metrics`

`/health` is the lightweight readiness endpoint for local checks and load balancers.

## Status endpoint

`GET /status` returns a JSON snapshot of the current key pool.

Typical fields:

- strategy
- storage backend
- upstream base URL
- key id
- total requests
- error count
- failover count
- estimated remaining quota
- last used time
- cooldown timestamp

## Metrics endpoint

`GET /metrics` returns Prometheus-compatible metrics.

PoolSwitch currently tracks:

- `poolswitch_requests_total`
- `poolswitch_failovers_total`
- `poolswitch_key_usage_total`
- `poolswitch_key_errors_total`
- `poolswitch_request_latency_seconds`
- `poolswitch_key_cooldown_active`

## Typical production setup

In production, teams usually:

- scrape `/metrics` with Prometheus
- alert when failovers spike
- alert when all keys are in cooldown
- monitor request latency and error rates

## Embedded mode note

In embedded mode, the same metrics objects still exist inside the process, but there is no HTTP `/metrics` route unless you also run the proxy server.
