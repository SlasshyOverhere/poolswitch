---
title: Proxy Mode
description: Run PoolSwitch as a local or shared HTTP gateway for any language.
---

# Proxy Mode

## Overview

Proxy mode is useful when your callers are not Python-only or Node-only.

Your app sends requests to PoolSwitch:

```text
app -> PoolSwitch proxy -> upstream API
```

The proxy owns:

- key selection
- retry and failover logic
- cooldown state
- metrics and status endpoints

## Start the server

```bash
poolswitch start --config poolswitch.example.yaml
```

## Built-in endpoints

- `GET /health`
- `GET /status`
- `GET /metrics`

All other provider-compatible paths are proxied upstream, for example:

- `POST /v1/chat/completions`
- `GET /v1/models`
- `POST /search`

## Example config

```yaml
listen_host: 127.0.0.1
listen_port: 8080
upstream_base_url: https://api.openai.com
auth_header_name: Authorization
auth_scheme: Bearer
strategy: quota_failover
retry_attempts: 3
cooldown_seconds: 3600
storage:
  backend: sqlite
  sqlite_path: poolswitch.db
keys:
  - id: primary
    value: sk-123
  - id: backup
    value: sk-456
```

## Calling the proxy

### Python

```python
from poolswitch_client import PoolSwitchClient

client = PoolSwitchClient("http://127.0.0.1:8080")
result = client.post(
    "/v1/chat/completions",
    json={
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello"}],
    },
)
```

### Node.js

```js
const { PoolSwitchProxyClient } = require("poolswitch-node");

const client = new PoolSwitchProxyClient("http://127.0.0.1:8080");
const result = await client.post("/v1/chat/completions", {
  json: {
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: "hello" }]
  }
});
```

### Go

```go
package main

import (
	"context"
	"fmt"

	poolswitch "github.com/SlasshyOverhere/poolswitch/sdk-go"
)

func main() {
	client := poolswitch.NewClient("http://127.0.0.1:8080")

	var out map[string]any
	_ = client.PostJSON(context.Background(), "/v1/chat/completions", map[string]any{
		"model": "gpt-4o-mini",
		"messages": []map[string]string{
			{"role": "user", "content": "hello"},
		},
	}, &out)

	fmt.Println(out)
}
```

## When to choose proxy mode

Use proxy mode when:

- multiple languages need the same gateway
- you want a shared pool for several services
- you want Prometheus metrics from one HTTP endpoint

If your app is already in JavaScript or TypeScript and does not need a shared gateway, use the [embedded Node.js client](/embedded-node) instead.
