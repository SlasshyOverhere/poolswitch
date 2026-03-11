# Architecture

## Overview

`poolswitch` is split into a language-agnostic local proxy and thin client SDKs.

Flow:

1. Application sends HTTP requests to `http://localhost:8080`.
2. The proxy selects a healthy key from the configured pool.
3. The proxy injects the provider auth header and forwards the request upstream.
4. If the upstream returns a retryable error or quota exhaustion, the proxy marks state, applies cooldowns, and retries with another key when allowed.
5. The final upstream response is returned to the caller unchanged except for hop-by-hop header cleanup.

## Components

- `poolswitch/config.py`: YAML, env, and CLI-compatible config loading.
- `poolswitch/storage/`: Memory, Redis, and SQLite persistence for key state.
- `poolswitch/strategies/`: Key selection algorithms.
- `poolswitch/core/key_pool.py`: Central state transitions for success, cooldown, failover, and key lifecycle.
- `poolswitch/core/quota.py`: Provider-agnostic quota and rate-limit classification.
- `poolswitch/retry/policy.py`: Exponential backoff with jitter.
- `poolswitch/proxy/app.py`: FastAPI proxy, metrics endpoint, status endpoint, and async request forwarding.
- `poolswitch/cli/main.py`: Binary-friendly operational interface.
- `sdk-python/`, `sdk-node/`, `sdk-go/`: Thin wrappers that simply target the proxy.

## Routing Strategies

- `round_robin`: Evenly rotates requests across available keys.
- `least_used`: Picks the key with the lowest observed request count.
- `random`: Random selection across healthy keys.
- `quota_failover`: Favors keys with the highest estimated remaining quota and the fewest recent rate-limit signals.

## Retry Model

Retries occur only before a successful upstream response is accepted by the caller.

- Network failures: retry with exponential backoff.
- `429`: retry and prefer a different key.
- Quota exhaustion payloads: place the key into cooldown and fail over.
- Safe methods are configurable through `retryable_methods`; by default the proxy allows POST because LLM/chat APIs commonly require it, but teams should use upstream idempotency keys when supported.

## Storage Model

Stored state per key:

- total requests
- last used time
- error count
- failover count
- estimated remaining quota
- cooldown timer
- consecutive rate-limit count

Definitions and secret values still come from config; runtime health/state is persisted in the configured store.

## Metrics

Prometheus-compatible `/metrics` includes:

- `poolswitch_requests_total`
- `poolswitch_failovers_total`
- `poolswitch_key_usage_total`
- `poolswitch_key_errors_total`
- `poolswitch_request_latency_seconds`
- `poolswitch_key_cooldown_active`

## Suggested Folder Structure

```text
/poolswitch
  /cli
  /core
  /proxy
  /retry
  /storage
  /strategies
/sdk-python
/sdk-node
/sdk-go
/tests
/docs
```

## SDK Usage

Python:

```python
from poolswitch_client import PoolSwitchClient

client = PoolSwitchClient("http://localhost:8080")
response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})
```

Node.js:

```js
const { PoolSwitchClient } = require("poolswitch-node");

const client = new PoolSwitchClient("http://localhost:8080");
const response = await client.post("/v1/chat/completions", {
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "hi" }],
});
```

Go:

```go
client := poolswitch.NewClient("http://localhost:8080")
var out map[string]any
err := client.PostJSON(ctx, "/v1/chat/completions", payload, &out)
```


