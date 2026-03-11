# PoolSwitch

PoolSwitch lets you use multiple API keys without writing your own rotation, retry, cooldown, or quota failover logic.

It supports two modes:

- embedded client inside your app
- optional local or shared proxy server

It is designed for APIs like OpenAI, Anthropic, Groq, Google, HuggingFace, or any HTTP API that authenticates with an API key header.

## What it handles

- key rotation
- quota failover
- retry with backoff
- per-key cooldowns
- local rate limiting
- memory, Redis, and SQLite state
- health, status, and Prometheus metrics in proxy mode

## Pick a mode

Use embedded mode when:

- your app is already in Python, Node.js, or TypeScript
- you do not want to run another service

Use proxy mode when:

- multiple apps need to share one key pool
- you want a language-agnostic HTTP endpoint

## Install

Python:

```bash
pip install poolswitch
```

Node.js:

```bash
npm install poolswitch-node
```

## Quickstart

### Embedded Node.js

```ts
import { PoolSwitchClient } from "poolswitch-node";

const client = new PoolSwitchClient({
  upstreamBaseUrl: "https://api.openai.com",
  keys: [
    { id: "openai-free-1", value: process.env.OPENAI_KEY_1! },
    { id: "openai-free-2", value: process.env.OPENAI_KEY_2! }
  ],
  strategy: "quota_failover"
});

const response = await client.post("/v1/chat/completions", {
  json: {
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: "Say hello from PoolSwitch." }]
  }
});

console.log(response.choices[0].message.content);
```

### Embedded Python

```python
from poolswitch import PoolSwitchClient

client = PoolSwitchClient(
    upstream_base_url="https://api.openai.com",
    keys=[
        {"id": "openai-free-1", "value": "sk-123"},
        {"id": "openai-free-2", "value": "sk-456"},
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

print(response["choices"][0]["message"]["content"])
```

### Async Python

```python
from poolswitch import AsyncPoolSwitchClient

async with AsyncPoolSwitchClient(
    upstream_base_url="https://api.openai.com",
    keys=["sk-123", "sk-456"],
) as client:
    response = await client.get("/v1/models")
    print(response["data"][0]["id"])
```

### Proxy mode

Create a config file:

```yaml
listen_host: 127.0.0.1
listen_port: 8080
upstream_base_url: https://api.openai.com
auth_header_name: Authorization
auth_scheme: Bearer
strategy: quota_failover
retry_attempts: 3
cooldown_seconds: 3600
keys:
  - id: openai-primary
    value: sk-123
  - id: openai-secondary
    value: sk-456
```

Start the proxy:

```bash
poolswitch start --config poolswitch.yaml
```

Send requests to the local endpoint:

```bash
curl -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

## Common options

Embedded clients support:

- `keys`
- `strategy`
- `retryAttempts` / `retry_attempts`
- `cooldownSeconds` / `cooldown_seconds`
- `authHeaderName` / `auth_header_name`
- `authScheme` / `auth_scheme`
- `rateLimitPerSecond` / `rate_limit_per_second`

Key strategies:

- `round_robin`
- `least_used`
- `random`
- `quota_failover`

## CLI

```bash
poolswitch start --config poolswitch.yaml
poolswitch status --config poolswitch.yaml
poolswitch metrics --config poolswitch.yaml
```

## Docs

Docs site:

- https://slasshyoverhere.github.io/poolswitch/

Local docs preview:

```bash
npm install
npm run docs:dev
```

Static build output:

```bash
npm run docs:build
```

The generated site is written to `docs/.vitepress/dist`.

## Packages

- Core Python package: `poolswitch`
- Node package: `poolswitch-node`
- Python proxy SDK package: `poolswitch-python`

## License

MIT
