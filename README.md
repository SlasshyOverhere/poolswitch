# PoolSwitch

`poolswitch` is a production-oriented API key proxy that rotates credentials, tracks quota state, retries safely, and exposes a language-agnostic HTTP interface.

It is designed for provider APIs such as OpenAI, Anthropic, Groq, Google, HuggingFace, or any generic HTTP endpoint that authenticates requests with an API key header.

## Features

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

