---
title: Configuration
description: Configure routing, retries, cooldowns, storage, and keys for embedded or proxy mode.
---

# Configuration

PoolSwitch configuration is shared across both modes:

- embedded clients
- proxy server

The same concepts apply in both cases:

- upstream API base URL
- auth header settings
- retry attempts
- cooldown duration
- rate limiting
- storage backend
- key definitions

## Example configuration

```yaml
listen_host: 127.0.0.1
listen_port: 8080
upstream_base_url: https://api.openai.com
auth_header_name: Authorization
auth_scheme: Bearer
strategy: quota_failover
retry_attempts: 3
cooldown_seconds: 3600
request_timeout_seconds: 60
connect_timeout_seconds: 10
rate_limit_per_second: 50
metrics_enabled: true
storage:
  backend: memory
  sqlite_path: poolswitch.db
  redis_url: redis://localhost:6379/0
  namespace: poolswitch
keys:
  - id: openai-primary
    value: sk-123
    monthly_quota: 10000
  - id: openai-secondary
    value: sk-456
```

## Settings reference

| Setting | Type | Default | Meaning |
| --- | --- | --- | --- |
| `listen_host` | `string` | `127.0.0.1` | IP address to bind the proxy to in server mode |
| `listen_port` | `integer` | `8080` | Port for the proxy server |
| `upstream_base_url` | `string` | required | Provider API base URL such as `https://api.openai.com` |
| `auth_header_name` | `string` | `Authorization` | Header used for authentication |
| `auth_scheme` | `string \| null` | `Bearer` | Prefix prepended to the key value; set to `null` for raw key headers |
| `strategy` | `string` | `round_robin` | `round_robin`, `least_used`, `random`, or `quota_failover` |
| `retry_attempts` | `integer` | `3` | Maximum attempts before returning the final error |
| `cooldown_seconds` | `integer` | `3600` | How long to disable a key after quota exhaustion |
| `rate_limit_per_second` | `number` | `50` | Local request shaping before calls are sent upstream |
| `keys` | `list` | required | API keys with optional `id`, `monthly_quota`, and `metadata` |
| `storage.backend` | `string` | `memory` | `memory`, `sqlite`, or `redis` |
| `retryable_methods` | `list` | `["GET", "HEAD", "OPTIONS", "DELETE", "POST"]` | HTTP methods PoolSwitch may retry automatically |

## Environment variables

Server deployments can also override config with environment variables such as:

- `POOLSWITCH_UPSTREAM_BASE_URL`
- `POOLSWITCH_KEYS`
- `POOLSWITCH_STRATEGY`
- `POOLSWITCH_RETRY_ATTEMPTS`
- `POOLSWITCH_COOLDOWN_SECONDS`
- `POOLSWITCH_STORAGE_BACKEND`
