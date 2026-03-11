---
title: Architecture
description: How PoolSwitch shares one core engine between embedded clients and the proxy server.
---

# Architecture

## Overview

PoolSwitch is built around one shared routing engine.

That core is reused in two product surfaces:

1. Embedded clients
2. Proxy server

In both modes, the same components handle state and failover.

## Components

- Embedded clients: direct in-process clients for Python and Node.js
- Proxy server: HTTP wrapper around the same routing engine for multi-language access
- Storage: memory, Redis, and SQLite persistence for key state
- Strategies: algorithms like `round_robin`, `least_used`, and `quota_failover`
- Core pool: central state transitions for success, cooldown, and key lifecycle
- Quota and retry: provider-agnostic quota evaluation and exponential backoff retry policies

## Request lifecycle

1. PoolSwitch selects a healthy key.
2. It injects the provider auth header.
3. It sends the upstream request.
4. It classifies the upstream result:
   - success
   - retryable rate limit
   - quota exhaustion
   - network failure
5. It updates key state, cooldowns, failovers, and metrics.
6. It returns the final parsed result or final error.

## Retry model

Retries occur only before a successful upstream response is accepted by the caller.

- Network failures: retry with exponential backoff
- `429`: retry and prefer a different key
- Quota exhaustion: place the key into cooldown and fail over
- Safe methods are configurable through `retryable_methods`

## Metrics

Prometheus-compatible `/metrics` includes:

- `poolswitch_requests_total`
- `poolswitch_failovers_total`
- `poolswitch_key_usage_total`
- `poolswitch_key_errors_total`
- `poolswitch_request_latency_seconds`
- `poolswitch_key_cooldown_active`
