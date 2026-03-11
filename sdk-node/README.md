# poolswitch-node

`poolswitch-node` is a lightweight Node.js client for PoolSwitch proxy servers.

It forwards requests to a local or remote proxy endpoint and keeps the client thin on purpose. The proxy handles key rotation, quota failover, retry logic, and observability.

## Install

```bash
npm install poolswitch-node
```

## Usage

```js
const { PoolSwitchClient } = require("poolswitch-node");

const client = new PoolSwitchClient("http://localhost:8080", {
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

### `new PoolSwitchClient(baseUrl, options?)`

- `baseUrl`: Proxy base URL such as `http://localhost:8080`
- `options.headers`: Default headers sent with every request
- `options.timeout`: Request timeout in milliseconds
- `options.fetchImpl`: Custom fetch implementation for testing or alternate runtimes

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
- JSON responses are parsed automatically when possible.
- Non-JSON responses are returned as text.


