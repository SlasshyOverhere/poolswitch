# poolswitch-node

`poolswitch-node` lets JavaScript and TypeScript apps use PoolSwitch in two ways:

- directly inside your app with the embedded `PoolSwitchClient`
- against a local or shared proxy with `PoolSwitchProxyClient`

## Install

```bash
npm install poolswitch-node
```

## Usage

### Embedded client

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

async function main() {
  const response = await client.post("/v1/chat/completions", {
    json: {
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "Hello from the embedded client" }]
    }
  });

  console.log(response.choices[0].message.content);
  console.log(client.status().keys);
}

main().catch((error) => {
  console.error(error.reason, error.status, error.data);
});
```

### Proxy client

```js
const { PoolSwitchProxyClient } = require("poolswitch-node");

const client = new PoolSwitchProxyClient("http://localhost:8080", {
  timeout: 30000,
  headers: {
    "x-app-name": "demo"
  }
});

async function main() {
  const response = await client.post("/v1/chat/completions", {
    json: {
      model: "gpt-4.1-mini",
      messages: [{ role: "user", content: "Hello from the proxy" }]
    }
  });

  console.log(response.status);
  console.log(response.data);
}

main().catch((error) => {
  console.error(error.status, error.data);
});
```

## API

### `new PoolSwitchClient(options)`

- `options.upstreamBaseUrl`: Upstream API base URL such as `https://api.openai.com`
- `options.keys`: Array of API keys as strings or `{ id, value, monthlyQuota }` objects
- `options.strategy`: `round_robin`, `least_used`, `random`, or `quota_failover`
- `options.retryAttempts`: Maximum attempts per request
- `options.cooldownSeconds`: Cooldown for quota-exhausted keys
- `options.authHeaderName`: Header name for key injection, default `Authorization`
- `options.authScheme`: Auth scheme, default `Bearer`
- `options.headers`: Default headers sent with every request
- `options.timeout`: Request timeout in milliseconds
- `options.fetchImpl`: Custom fetch implementation for tests or alternate runtimes

### `new PoolSwitchProxyClient(baseUrl, options?)`

- `baseUrl`: Proxy base URL such as `http://localhost:8080`
- `options.headers`: Default headers sent with every request
- `options.timeout`: Request timeout in milliseconds
- `options.fetchImpl`: Custom fetch implementation for testing or alternate runtimes

### Embedded client methods

- `client.get(path, options?)`
- `client.post(path, options?)`
- `client.put(path, options?)`
- `client.patch(path, options?)`
- `client.delete(path, options?)`
- `client.status()`

Embedded responses return parsed JSON for JSON APIs, or plain text for text responses.

### Proxy client methods

### `client.request(method, path, options?)`

Supported options:

- `headers`: Per-request headers
- `json`: JSON-serializable request body
- `body`: Raw request body
- `query`: Query string object
- `timeout`: Per-request timeout override
- `signal`: Optional `AbortSignal`

Returns:

- `status`
- `ok`
- `headers`
- `data`
- `text`

Errors:

- Throws `PoolSwitchError` for non-2xx responses or transport failures.
- `error.data` includes parsed JSON when available.

### Convenience methods

- `client.get(path, options?)`
- `client.post(path, options?)`
- `client.put(path, options?)`
- `client.patch(path, options?)`
- `client.delete(path, options?)`

## Notes

- Requires Node.js 18 or newer because it uses the built-in `fetch`.
- Supports both ESM `import` and CommonJS `require`.
- JSON responses are parsed automatically when possible.
- Non-JSON responses are returned as text.


