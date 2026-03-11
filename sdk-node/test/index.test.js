'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { PoolSwitchClient, PoolSwitchError } = require('../src/index.js');

const { Response } = globalThis;

function makeJsonResponse(status, payload) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' }
  });
}

test('constructor validates baseUrl and fetch impl', () => {
  assert.throws(() => new PoolSwitchClient(''), /baseUrl must be/);
  assert.throws(() => new PoolSwitchClient(123), /baseUrl must be/);
  assert.throws(() => new PoolSwitchClient('https://example.com', { fetchImpl: 123 }), /fetch implementation/);
});

test('request builds url, headers, and json body', async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return makeJsonResponse(200, { ok: true });
  };

  const client = new PoolSwitchClient('https://example.com/', {
    fetchImpl,
    headers: { 'X-Default': 'yes' }
  });

  const result = await client.post('/v1/demo', {
    json: { hello: 'world' },
    query: { a: 1, b: [2, 3], c: null }
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.data, { ok: true });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://example.com/v1/demo?a=1&b=2&b=3');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.headers['x-default'], 'yes');
  assert.equal(calls[0].options.headers['content-type'], 'application/json');
});

test('request returns text when non-json', async () => {
  const fetchImpl = async () => new Response('hello', { status: 200, headers: { 'content-type': 'text/plain' } });
  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  const result = await client.get('v1/demo');
  assert.equal(result.data, 'hello');
});

test('request throws PoolSwitchError on non-2xx', async () => {
  const fetchImpl = async () => makeJsonResponse(400, { error: 'bad' });
  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  await assert.rejects(
    () => client.get('/v1/demo'),
    (err) => {
      assert.ok(err instanceof PoolSwitchError);
      assert.equal(err.status, 400);
      assert.deepEqual(err.data, { error: 'bad' });
      return true;
    }
  );
});

test('request wraps fetch errors', async () => {
  const fetchImpl = async () => {
    throw new Error('boom');
  };
  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  await assert.rejects(
    () => client.get('/v1/demo'),
    (err) => {
      assert.ok(err instanceof PoolSwitchError);
      assert.ok(err.text.includes('boom'));
      return true;
    }
  );
});

test('request wraps errors without message', async () => {
  const fetchImpl = async () => {
    throw {};
  };
  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  await assert.rejects(
    () => client.get('/v1/demo'),
    (err) => {
      assert.ok(err instanceof PoolSwitchError);
      assert.equal(err.text, null);
      return true;
    }
  );
});

test('request wraps null error', async () => {
  const fetchImpl = async () => {
    throw null;
  };
  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  await assert.rejects(
    () => client.get('/v1/demo'),
    (err) => {
      assert.ok(err instanceof PoolSwitchError);
      assert.equal(err.text, null);
      return true;
    }
  );
});

test('parseResponse handles invalid json body', async () => {
  const fetchImpl = async () => new Response('{invalid', { status: 200, headers: { 'content-type': 'text/plain' } });
  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  const result = await client.get('/v1/demo');
  assert.equal(result.data, '{invalid');
});

test('parseResponse without content-type header', async () => {
  const fetchImpl = async () => new Response(null, { status: 200 });
  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  const result = await client.get('/v1/demo');
  assert.equal(result.data, '');
});

test('request without timeout uses defaults', async () => {
  const fetchImpl = async () => makeJsonResponse(200, { ok: true });
  const client = new PoolSwitchClient('https://example.com', { fetchImpl, timeout: 0 });

  const result = await client.get('/v1/demo', { timeout: 0 });
  assert.equal(result.ok, true);
});

test('request handles active abort signal', async () => {
  const controller = new AbortController();
  let sawAbort = false;

  const fetchImpl = async (_url, options) =>
    new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        sawAbort = true;
        reject(options.signal.reason);
      });
    });

  const client = new PoolSwitchClient('https://example.com', { fetchImpl });
  const promise = client.get('/v1/demo', { signal: controller.signal });
  controller.abort(new Error('stop'));

  await assert.rejects(
    () => promise,
    (err) => err instanceof PoolSwitchError
  );
  assert.equal(sawAbort, true);
});

test('request respects external abort signal', async () => {
  const controller = new AbortController();
  controller.abort(new Error('stop'));

  const fetchImpl = async (_url, options) => {
    assert.equal(options.signal.aborted, true);
    throw options.signal.reason;
  };

  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  await assert.rejects(
    () => client.get('/v1/demo', { signal: controller.signal }),
    (err) => err instanceof PoolSwitchError
  );
});

test('request times out via abort', async () => {
  const fetchImpl = (_url, options) =>
    new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        reject(options.signal.reason);
      });
    });

  const client = new PoolSwitchClient('https://example.com', { fetchImpl, timeout: 5 });

  await assert.rejects(
    () => client.get('/v1/demo', { timeout: 5 }),
    (err) => err instanceof PoolSwitchError
  );
});

test('http verb helpers delegate to request', async () => {
  const methods = [];
  const fetchImpl = async (_url, options) => {
    methods.push(options.method);
    return makeJsonResponse(200, { ok: true });
  };
  const client = new PoolSwitchClient('https://example.com', { fetchImpl });

  await client.put('/v1/demo');
  await client.patch('/v1/demo');
  await client.delete('/v1/demo');

  assert.deepEqual(methods, ['PUT', 'PATCH', 'DELETE']);
});

test('uses default fetch implementation when not provided', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return makeJsonResponse(200, { ok: true });
  };

  try {
    const client = new PoolSwitchClient('https://example.com');
    const result = await client.get('/v1/demo');
    assert.equal(result.ok, true);
    assert.equal(calls.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('PoolSwitchError defaults text to null', () => {
  const error = new PoolSwitchError('oops', {});
  assert.equal(error.text, null);
});

test('abort listener cleanup without timeout', async () => {
  const controller = new AbortController();
  const fetchImpl = async () => makeJsonResponse(200, { ok: true });
  const client = new PoolSwitchClient('https://example.com', { fetchImpl, timeout: 0 });

  const result = await client.get('/v1/demo', { signal: controller.signal, timeout: 0 });
  assert.equal(result.ok, true);
});


