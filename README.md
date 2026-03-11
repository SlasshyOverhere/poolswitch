# PoolSwitch

`poolswitch` is a production-oriented API key rotation toolkit that can run either:

- directly inside your app as an embedded client
- as a local or shared proxy server

It is designed for provider APIs such as OpenAI, Anthropic, Groq, Google, HuggingFace, or any generic HTTP endpoint that authenticates requests with an API key header.

## Features

- Embedded Python client with built-in key rotation, retry, cooldown, and quota failover
- Async local HTTP proxy with low overhead
- Key rotation strategies: `round_robin`, `least_used`, `random`, `quota_failover`
- Quota-aware cooldowns and automatic failover
- Retry system with exponential backoff and network/429 handling
- Pluggable storage: memory, Redis, SQLite
- YAML, environment variable, and CLI configuration
- Prometheus-compatible `/metrics` endpoint
- CLI commands for startup, status, metrics, and key management
- Thin SDKs for Python, Node.js, and Go

## Quick Start

### Embedded Client (Recommended)

```python
from poolswitch import PoolSwitchClient

client = PoolSwitchClient(
    upstream_base_url="https://api.openai.com",
    keys=[
        {"id": "primary", "value": "sk-123"},
        {"id": "backup", "value": "sk-456"},
    ],
    strategy="quota_failover",
    retry_attempts=3,
    cooldown_seconds=3600,
)

response = client.post(
    "/v1/chat/completions",
    json={
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello"}],
    },
)
```

For async apps:

```python
from poolswitch import AsyncPoolSwitchClient

async with AsyncPoolSwitchClient(
    upstream_base_url="https://api.openai.com",
    keys=["sk-123", "sk-456"],
) as client:
    response = await client.get("/v1/models")
```

### Proxy Mode

```bash
pip install -e .
poolswitch start --config poolswitch.example.yaml
```

Example request:

```bash
curl -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

See [`docs/architecture.md`](./docs/architecture.md) for the design and the SDK folders for client usage.

