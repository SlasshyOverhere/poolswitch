'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  PoolSwitchClient,
  PoolSwitchProxyClient,
  PoolSwitchError
} = require('../src/index.js');

const { Response } = globalThis;

function makeJsonResponse(status, payload, headers = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json', ...headers }
  });
}

function headerValue(headers, name) {
  const match = Object.entries(headers).find(([key]) => key.toLowerCase() === name.toLowerCase());
  return match ? match[1] : undefined;
}

test('proxy constructor validates baseUrl and fetch impl', () => {
  assert.throws(() => new PoolSwitchProxyClient(''), /baseUrl must be/);
  assert.throws(() => new PoolSwitchProxyClient(123), /baseUrl must be/);
  assert.throws(() => new PoolSwitchProxyClient('https://example.com', { fetchImpl: 123 }), /fetch implementation/);
});

test('proxy request builds url, headers, and json body', async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return makeJsonResponse(200, { ok: true });
  };

  const client = new PoolSwitchProxyClient('https://example.com/', {
    fetchImpl,
    headers: { 'X-Default': 'yes' }
  });

  const result = await client.post('/v1/demo', {
    json: { hello: 'world' },
    query: { a: 1, b: [2, 3], c: null }
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.data, { ok: true });
  assert.equal(calls[0].url, 'https://example.com/v1/demo?a=1&b=2&b=3');
  assert.equal(calls[0].options.headers['x-default'], 'yes');
  assert.equal(calls[0].options.headers['content-type'], 'application/json');
});

test('proxy request handles text success and typed failures', async () => {
  const okClient = new PoolSwitchProxyClient('https://example.com', {
    fetchImpl: async () => new Response('hello', { status: 200, headers: { 'content-type': 'text/plain' } })
  });
  const textResult = await okClient.get('/v1/demo');
  assert.equal(textResult.data, 'hello');

  const badClient = new PoolSwitchProxyClient('https://example.com', {
    fetchImpl: async () => makeJsonResponse(400, { error: 'bad' })
  });

  await assert.rejects(
    () => badClient.get('/v1/demo'),
    (error) => {
      assert.ok(error instanceof PoolSwitchError);
      assert.equal(error.status, 400);
      assert.deepEqual(error.data, { error: 'bad' });
      return true;
    }
  );
});

test('proxy request wraps transport and abort errors', async () => {
  const boomClient = new PoolSwitchProxyClient('https://example.com', {
    fetchImpl: async () => {
      throw new Error('boom');
    }
  });
  await assert.rejects(
    () => boomClient.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && error.text === 'boom'
  );

  const nullClient = new PoolSwitchProxyClient('https://example.com', {
    fetchImpl: async () => {
      throw null;
    }
  });
  await assert.rejects(
    () => nullClient.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && error.text === null
  );

  const controller = new AbortController();
  const abortClient = new PoolSwitchProxyClient('https://example.com', {
    fetchImpl: async (_url, options) =>
      new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(options.signal.reason));
      }),
    timeout: 5
  });
  const promise = abortClient.get('/v1/demo', { signal: controller.signal, timeout: 0 });
  controller.abort(new Error('stop'));
  await assert.rejects(() => promise, (error) => error instanceof PoolSwitchError);

  const preAbortedController = new AbortController();
  preAbortedController.abort(new Error('already stopped'));
  const preAbortedClient = new PoolSwitchProxyClient('https://example.com', {
    fetchImpl: async (_url, options) => {
      throw options.signal.reason;
    }
  });
  await assert.rejects(
    () => preAbortedClient.get('/v1/demo', { signal: preAbortedController.signal, timeout: 0 }),
    (error) => error instanceof PoolSwitchError && error.text === 'already stopped'
  );

  const timeoutClient = new PoolSwitchProxyClient('https://example.com', {
    timeout: 5,
    fetchImpl: async (_url, options) => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      throw options.signal.reason;
    }
  });
  await assert.rejects(
    () => timeoutClient.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && /timed out/i.test(error.text)
  );
});

test('proxy parse helpers cover invalid json, missing content-type, default fetch, and helper verbs', async () => {
  const invalidJsonClient = new PoolSwitchProxyClient('https://example.com', {
    fetchImpl: async () => new Response('{invalid', { status: 200, headers: { 'content-type': 'text/plain' } })
  });
  assert.equal((await invalidJsonClient.get('/v1/demo')).data, '{invalid');

  const noTypeClient = new PoolSwitchProxyClient('https://example.com', {
    fetchImpl: async () => new Response(null, { status: 200 })
  });
  assert.equal((await noTypeClient.get('/v1/demo')).data, '');

  const methods = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_url, options) => {
    methods.push(options.method);
    return makeJsonResponse(200, { ok: true });
  };

  try {
    const client = new PoolSwitchProxyClient('https://example.com', { timeout: 0 });
    await client.get('/v1/demo', { timeout: 0 });
    await client.put('/v1/demo');
    await client.patch('/v1/demo');
    await client.delete('/v1/demo');
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(methods, ['GET', 'PUT', 'PATCH', 'DELETE']);
});

test('embedded constructor validates options', () => {
  assert.throws(() => new PoolSwitchClient(null), /options must be an object/);
  assert.throws(() => new PoolSwitchClient({}), /upstreamBaseUrl must be/);
  assert.throws(() => new PoolSwitchClient({ upstreamBaseUrl: 'https://api.example.com', keys: [] }), /keys must be/);
  assert.throws(
    () => new PoolSwitchClient({ upstreamBaseUrl: 'https://api.example.com', keys: [123] }),
    /each key must be/
  );
  assert.throws(
    () =>
      new PoolSwitchClient({
        upstreamBaseUrl: 'https://api.example.com',
        keys: ['sk-1'],
        fetchImpl: 123
      }),
    /fetch implementation/
  );
  assert.throws(
    () =>
      new PoolSwitchClient({
        upstreamBaseUrl: 'https://api.example.com',
        keys: ['sk-1'],
        strategy: 'bad'
      }),
    /strategy must be/
  );
});

test('PoolSwitchError exposes reason', () => {
  const error = new PoolSwitchError('oops', { reason: 'rate_limited' });
  assert.equal(error.reason, 'rate_limited');
  assert.equal(error.text, null);
});

test('embedded request headers status and key normalization work', () => {
  const client = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: [
      'sk-1',
      { id: 'second', value: 'sk-2', monthlyQuota: 10, metadata: { tier: 'free' } }
    ],
    headers: { Authorization: 'old', 'X-App': 'demo' },
    authHeaderName: 'X-API-Key',
    authScheme: null,
    fetchImpl: async () => makeJsonResponse(200, { ok: true })
  });

  const headers = client.requestHeaders({ 'x-request': '1', 'x-api-key': 'ignore-me' }, client.keyDefinitions[0]);
  assert.equal(headerValue(headers, 'x-api-key'), 'sk-1');
  assert.equal(headers['x-app'], 'demo');
  assert.equal(headers['x-request'], '1');

  const status = client.status();
  assert.equal(status.keys[0].id, 'key-1');
  assert.equal(status.keys[1].id, 'second');
  assert.equal(status.keys[0].estimatedRemainingQuota, null);
  assert.equal(status.keys[1].estimatedRemainingQuota, 10);

  const fallbackIdClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: [{ id: '', value: 'sk-blank' }],
    fetchImpl: async () => makeJsonResponse(200, { ok: true })
  });
  assert.equal(fallbackIdClient.status().keys[0].id, 'key-1');
});

test('embedded client returns json and text data', async () => {
  const jsonClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    fetchImpl: async (_url, options) => {
      assert.equal(headerValue(options.headers, 'authorization'), 'Bearer sk-1');
      return makeJsonResponse(200, { ok: true }, { 'x-ratelimit-remaining': '7.4' });
    }
  });
  assert.deepEqual(await jsonClient.get('/v1/demo'), { ok: true });
  assert.equal(jsonClient.status().keys[0].estimatedRemainingQuota, 7);

  const textClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com/base',
    keys: [{ id: 'plain', value: 'sk-plain' }],
    authHeaderName: 'X-Api-Key',
    authScheme: null,
    fetchImpl: async (_url, options) => {
      assert.equal(headerValue(options.headers, 'x-api-key'), 'sk-plain');
      return new Response('pong', { status: 200, headers: { 'content-type': 'text/plain' } });
    }
  });
  assert.equal(await textClient.get('v1/ping'), 'pong');
});

test('embedded network retry and no-retry errors work', async () => {
  let calls = 0;
  const retryClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1', 'sk-2'],
    retryAttempts: 2,
    sleep: async () => {},
    fetchImpl: async () => {
      calls += 1;
      if (calls === 1) {
        throw new Error('boom');
      }
      return makeJsonResponse(200, { ok: true });
    }
  });
  assert.deepEqual(await retryClient.get('/v1/demo'), { ok: true });

  const failClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async () => {
      throw new Error('offline');
    }
  });
  await assert.rejects(
    () => failClient.patch('/v1/demo', { json: { ok: true } }),
    (error) => error instanceof PoolSwitchError && error.reason === 'network_error'
  );

  const nullErrorClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async () => {
      throw null;
    }
  });
  await assert.rejects(
    () => nullErrorClient.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && error.reason === 'network_error' && error.text === null
  );
});

test('embedded quota failover and no healthy keys are handled', async () => {
  const authHeaders = [];
  const client = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1', 'sk-2'],
    retryAttempts: 3,
    sleep: async () => {},
    fetchImpl: async (_url, options) => {
      authHeaders.push(headerValue(options.headers, 'authorization'));
      if (authHeaders.length === 1) {
        return makeJsonResponse(429, { error: { message: 'quota exceeded' } });
      }
      return makeJsonResponse(200, { ok: true });
    }
  });

  assert.deepEqual(await client.post('/v1/demo', { json: { hello: 'world' } }), { ok: true });
  const status = client.status();
  assert.deepEqual(authHeaders, ['Bearer sk-1', 'Bearer sk-2']);
  assert.ok(status.keys[0].cooldownUntil);
  assert.equal(status.keys[1].totalRequests, 1);

  const exhaustedClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 2,
    sleep: async () => {},
    fetchImpl: async () => makeJsonResponse(429, { error: { message: 'quota exceeded' } })
  });
  await assert.rejects(
    () => exhaustedClient.post('/v1/demo', { json: { hello: 'world' } }),
    (error) => error instanceof PoolSwitchError && error.reason === 'no_healthy_keys'
  );
});

test('embedded rate limit retry, quota retry exhaustion, and retry-after are classified correctly', async () => {
  let calls = 0;
  const retryClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1', 'sk-2'],
    retryAttempts: 2,
    sleep: async () => {},
    fetchImpl: async () => {
      calls += 1;
      if (calls === 1) {
        return makeJsonResponse(429, { error: { message: 'Slow down' } });
      }
      return makeJsonResponse(200, { ok: true });
    }
  });
  assert.deepEqual(await retryClient.get('/v1/demo'), { ok: true });

  const quotaClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async () => makeJsonResponse(429, { error: { message: 'quota exceeded' } })
  });
  await assert.rejects(
    () => quotaClient.post('/v1/demo', { json: { hello: 'world' } }),
    (error) =>
      error instanceof PoolSwitchError &&
      error.reason === 'quota_exceeded' &&
      error.status === 429
  );

  const retryAfterClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async () => makeJsonResponse(503, { error: 'busy' }, { 'retry-after': '1' })
  });
  await assert.rejects(
    () => retryAfterClient.get('/v1/demo'),
    (error) =>
      error instanceof PoolSwitchError &&
      error.reason === 'upstream_retry_after' &&
      error.status === 503
  );
});

test('embedded non-retryable upstream errors still update state and include parsed data', async () => {
  const remainingClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    fetchImpl: async () =>
      makeJsonResponse(400, { usage: { remaining_quota: 3 }, error: 'bad request' })
  });
  await assert.rejects(
    () => remainingClient.get('/v1/demo'),
    (error) =>
      error instanceof PoolSwitchError &&
      error.status === 400 &&
      error.data.error === 'bad request'
  );
  assert.equal(remainingClient.status().keys[0].estimatedRemainingQuota, 3);
  assert.equal(remainingClient.status().keys[0].totalRequests, 1);

  const nonIntegerQuotaClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    fetchImpl: async () => makeJsonResponse(200, { usage: { remaining_quota: 'soon' }, ok: true })
  });
  assert.deepEqual(await nonIntegerQuotaClient.get('/v1/demo'), { usage: { remaining_quota: 'soon' }, ok: true });
  assert.equal(nonIntegerQuotaClient.status().keys[0].estimatedRemainingQuota, null);
});

test('embedded auth and rate-limit helpers cover edge paths', async () => {
  const delayed = [];
  const client = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    rateLimitPerSecond: 1,
    sleep: async (seconds) => {
      delayed.push(seconds);
      client.requestTimestamps = [];
    },
    fetchImpl: async () => makeJsonResponse(200, { ok: true }),
    timeout: 0
  });

  client.requestTimestamps = [Date.now()];
  await client.acquireRateLimit();
  assert.equal(delayed.length, 1);

  const controller = new AbortController();
  controller.abort(new Error('stop'));
  const abortClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async (_url, options) => {
      throw options.signal.reason;
    }
  });
  await assert.rejects(
    () => abortClient.get('/v1/demo', { signal: controller.signal }),
    (error) => error instanceof PoolSwitchError && error.reason === 'network_error'
  );
});

test('embedded strategies choose keys as expected', async () => {
  const roundRobinHeaders = [];
  const roundRobinClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1', 'sk-2'],
    strategy: 'round_robin',
    fetchImpl: async (_url, options) => {
      roundRobinHeaders.push(headerValue(options.headers, 'authorization'));
      return makeJsonResponse(200, { ok: true });
    }
  });
  await roundRobinClient.get('/one');
  await roundRobinClient.get('/two');
  assert.deepEqual(roundRobinHeaders, ['Bearer sk-1', 'Bearer sk-2']);

  const leastUsedHeaders = [];
  const leastUsedClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1', 'sk-2'],
    strategy: 'least_used',
    fetchImpl: async (_url, options) => {
      leastUsedHeaders.push(headerValue(options.headers, 'authorization'));
      return makeJsonResponse(200, { ok: true });
    }
  });
  await leastUsedClient.get('/one');
  await leastUsedClient.get('/two');
  assert.deepEqual(leastUsedHeaders, ['Bearer sk-1', 'Bearer sk-2']);

  const randomHeaders = [];
  const randomClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1', 'sk-2'],
    strategy: 'random',
    random: () => 0.99,
    fetchImpl: async (_url, options) => {
      randomHeaders.push(headerValue(options.headers, 'authorization'));
      return makeJsonResponse(200, { ok: true });
    }
  });
  await randomClient.get('/one');
  assert.deepEqual(randomHeaders, ['Bearer sk-2']);

  const methods = [];
  const verbClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    fetchImpl: async (_url, options) => {
      methods.push(options.method);
      return makeJsonResponse(200, { ok: true });
    }
  });
  await verbClient.put('/put');
  await verbClient.delete('/delete');
  assert.deepEqual(methods, ['PUT', 'DELETE']);
});

test('embedded direct state mutation helpers cover remaining branches', () => {
  const client = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    fetchImpl: async () => makeJsonResponse(200, { ok: true })
  });

  client.recordTransientError('key-1', 'rate_limited');
  assert.equal(client.states.get('key-1').consecutiveRateLimits, 1);

  client.markKeyQuotaExhausted('key-1');
  assert.equal(client.states.get('key-1').estimatedRemainingQuota, 0);
  client.markKeyQuotaExhausted('key-1');
  assert.equal(client.states.get('key-1').estimatedRemainingQuota, 0);

  client.recordFailover('key-1');
  assert.equal(client.states.get('key-1').failoverCount, 1);

  client.recordSuccess('key-1', 8);
  assert.equal(client.states.get('key-1').consecutiveRateLimits, 0);
  assert.equal(client.states.get('key-1').cooldownUntil, null);
  assert.equal(client.states.get('key-1').estimatedRemainingQuota, 8);

  client.states.get('key-1').cooldownUntil = new Date(Date.now() - 1000).toISOString();
  assert.equal(client.acquireKey().definition.id, 'key-1');
});

test('embedded unknown 429 and 401 quota messages are handled', async () => {
  const generic429Client = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async () => makeJsonResponse(429, { error: { message: 'Please retry later' } })
  });
  await assert.rejects(
    () => generic429Client.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && error.reason === 'rate_limited'
  );

  const authQuotaClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async () => makeJsonResponse(401, { error: { message: 'insufficient_quota' } })
  });
  await assert.rejects(
    () => authQuotaClient.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && error.reason === 'quota_exceeded'
  );
});

test('embedded timeout, listener cleanup, quota header parsing, and comparator edge branches are covered', async () => {
  const timeoutClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    timeout: 5,
    fetchImpl: async (_url, options) => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      throw options.signal.reason;
    }
  });
  await assert.rejects(
    () => timeoutClient.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && error.reason === 'network_error' && /timed out/i.test(error.text)
  );

  let abortListeners = 0;
  const controller = new AbortController();
  let listenerReady;
  const ready = new Promise((resolve) => {
    listenerReady = resolve;
  });
  const listenerClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async (_url, options) =>
      new Promise((_resolve, reject) => {
        if (options.signal.aborted) {
          reject(options.signal.reason);
          return;
        }
        options.signal.addEventListener('abort', () => reject(options.signal.reason));
        listenerReady();
      })
  });
  const originalAdd = controller.signal.addEventListener.bind(controller.signal);
  const originalRemove = controller.signal.removeEventListener.bind(controller.signal);
  controller.signal.addEventListener = (...args) => {
    abortListeners += 1;
    return originalAdd(...args);
  };
  controller.signal.removeEventListener = (...args) => {
    abortListeners -= 1;
    return originalRemove(...args);
  };
  const promise = listenerClient.get('/v1/demo', { signal: controller.signal });
  await ready;
  controller.abort(new Error('stop'));
  await assert.rejects(() => promise, (error) => error instanceof PoolSwitchError && error.reason === 'network_error');
  assert.equal(abortListeners, 0);

  const headerQuotaClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    fetchImpl: async () => makeJsonResponse(200, { ok: true }, { 'x-remaining-quota': '12.5' })
  });
  assert.deepEqual(await headerQuotaClient.get('/v1/demo'), { ok: true });
  assert.equal(headerQuotaClient.status().keys[0].estimatedRemainingQuota, 12);

  const arrayMessageClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async () =>
      makeJsonResponse(429, { error: [null, 'Too many requests'] })
  });
  await assert.rejects(
    () => arrayMessageClient.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && error.reason === 'rate_limited'
  );

  const textFallbackClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1'],
    retryAttempts: 1,
    fetchImpl: async () =>
      new Response('0', { status: 429, headers: { 'content-type': 'application/json' } })
  });
  await assert.rejects(
    () => textFallbackClient.get('/v1/demo'),
    (error) => error instanceof PoolSwitchError && error.reason === 'rate_limited'
  );

  const compareClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: ['sk-1', 'sk-2', 'sk-3'],
    strategy: 'least_used',
    fetchImpl: async () => makeJsonResponse(200, { ok: true })
  });
  compareClient.states.get('key-2').errorCount = 1;
  assert.equal(compareClient.acquireKey().definition.id, 'key-1');

  const quotaPriorityClient = new PoolSwitchClient({
    upstreamBaseUrl: 'https://api.example.com',
    keys: [
      { id: 'known', value: 'sk-1', monthlyQuota: 5 },
      { id: 'unknown', value: 'sk-2' }
    ],
    strategy: 'quota_failover',
    fetchImpl: async () => makeJsonResponse(200, { ok: true })
  });
  assert.equal(quotaPriorityClient.acquireKey().definition.id, 'known');

  await compareClient.sleep(0);
});
