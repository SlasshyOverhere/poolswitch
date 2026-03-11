---
title: Quickstart
description: Start rotating API keys in your app or behind a local proxy in under five minutes.
---

# Quickstart

## Install

### Python

```bash
pip install poolswitch
```

### Node.js and TypeScript

```bash
npm install poolswitch-node
```

## Pick the easiest mode

- Embedded client: best for Python, Node.js, and TypeScript apps
- Proxy server: best for shared internal gateways or multi-language stacks

## Embedded Node.js example

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

What PoolSwitch handles for you:

- selecting the next healthy key
- injecting the auth header
- retrying safe failures
- cooling down exhausted keys
- failing over to another account

## Embedded Python example

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

For async Python apps:

```python
from poolswitch import AsyncPoolSwitchClient

async with AsyncPoolSwitchClient(
    upstream_base_url="https://api.openai.com",
    keys=["sk-123", "sk-456"],
) as client:
    response = await client.get("/v1/models")
    print(response["data"][0]["id"])
```

## Proxy mode example

Create `poolswitch.yaml`:

```yaml
listen_host: 127.0.0.1
listen_port: 8080
upstream_base_url: https://api.openai.com
auth_header_name: Authorization
auth_scheme: Bearer
strategy: quota_failover
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

Check it:

```bash
curl http://127.0.0.1:8080/health
```

Send a provider-compatible request:

```bash
curl -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

## Next steps

- [Embedded Node.js guide](/embedded-node)
- [Embedded Python guide](/embedded-python)
- [Configuration reference](/configuration)
- [Deployment guide](/deployment)
