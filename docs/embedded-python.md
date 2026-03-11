---
title: Embedded Python Client
description: Use PoolSwitch directly inside a Python application without running a separate server.
---

# Embedded Python Client

## Overview

The embedded Python client is the easiest way to use PoolSwitch.

Instead of running a local proxy and pointing your app at `localhost`, you import a client and give it:

- the upstream API base URL
- a list of keys
- a routing strategy
- optional retry, cooldown, and storage settings

## Synchronous client

```python
from poolswitch import PoolSwitchClient

client = PoolSwitchClient(
    upstream_base_url="https://api.openai.com",
    keys=[
        {"id": "openai-free-1", "value": "sk-aaa"},
        {"id": "openai-free-2", "value": "sk-bbb"},
        {"id": "openai-free-3", "value": "sk-ccc"},
    ],
    strategy="quota_failover",
    retry_attempts=3,
    cooldown_seconds=3600,
)

response = client.post(
    "/v1/chat/completions",
    json={
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Write a one-line summary of PoolSwitch."}
        ],
    },
)

print(response["choices"][0]["message"]["content"])
```

## Async client

```python
from poolswitch import AsyncPoolSwitchClient

async with AsyncPoolSwitchClient(
    upstream_base_url="https://api.openai.com",
    keys=["sk-aaa", "sk-bbb", "sk-ccc"],
    strategy="quota_failover",
) as client:
    response = await client.get("/v1/models")
    print(response["data"][0]["id"])
```

## Supported key formats

- plain strings
- dictionaries with `id`, `value`, and optional metadata
- `KeyConfig` objects

```python
from poolswitch import PoolSwitchClient

client = PoolSwitchClient(
    upstream_base_url="https://api.openai.com",
    keys=[
        "sk-aaa",
        {"id": "free-2", "value": "sk-bbb", "monthly_quota": 100},
        {"id": "paid", "value": "sk-ccc", "metadata": {"tier": "pro"}},
    ],
)
```

## What the client does for you

When you call `get`, `post`, `put`, `patch`, or `delete`, PoolSwitch automatically:

- chooses a healthy key
- injects the configured auth header
- retries network failures and retryable `429` responses
- cools down quota-exhausted keys
- fails over to the next key when needed

## Inspect status

```python
status = client.status()
print(status)
```

That includes:

- total requests per key
- error counts
- failover counts
- estimated remaining quota
- cooldown timestamps

## When to choose embedded Python mode

Use embedded mode when:

- your app is already written in Python
- you want zero extra infrastructure
- each service should manage its own key pool locally

Use proxy mode instead when:

- non-Python services need access
- multiple apps should share the same pool over HTTP
- you want one internal gateway for many consumers
