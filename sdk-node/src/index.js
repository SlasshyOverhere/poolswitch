"use strict";

class PoolSwitchError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "PoolSwitchError";
    this.status = details.status ?? null;
    this.headers = details.headers ?? {};
    this.data = details.data;
    this.text = details.text ?? null;
    this.cause = details.cause;
  }
}

class PoolSwitchClient {
  constructor(baseUrl, options = {}) {
    if (!baseUrl || typeof baseUrl !== "string") {
      throw new TypeError("baseUrl must be a non-empty string");
    }

    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.defaultHeaders = normalizeHeaders(options.headers);
    this.timeout = options.timeout ?? 30000;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;

    if (typeof this.fetchImpl !== "function") {
      throw new TypeError("A fetch implementation is required");
    }
  }

  async request(method, path, options = {}) {
    const url = buildUrl(this.baseUrl, path, options.query);
    const headers = {
      ...this.defaultHeaders,
      ...normalizeHeaders(options.headers)
    };

    const hasJson = Object.prototype.hasOwnProperty.call(options, "json");
    const body = hasJson ? JSON.stringify(options.json) : options.body;

    if (hasJson && headers["content-type"] === undefined) {
      headers["content-type"] = "application/json";
    }

    const controller = new AbortController();
    const timeout = options.timeout ?? this.timeout;
    const externalSignal = options.signal;
    let timeoutId = null;
    let removeAbortListener = () => {};

    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort(externalSignal.reason);
      } else {
        const onAbort = () => controller.abort(externalSignal.reason);
        externalSignal.addEventListener("abort", onAbort, { once: true });
        removeAbortListener = () => {
          externalSignal.removeEventListener("abort", onAbort);
        };
      }
    }

    if (timeout && Number.isFinite(timeout) && timeout > 0) {
      timeoutId = setTimeout(() => {
        controller.abort(new Error(`Request timed out after ${timeout}ms`));
      }, timeout);
    }

    let parsed = null;
    let caughtError = null;

    try {
      const response = await this.fetchImpl(url, {
        method: method.toUpperCase(),
        headers,
        body,
        signal: controller.signal
      });

      parsed = await parseResponse(response);
      if (!response.ok) {
        caughtError = new PoolSwitchError(
          `Proxy request failed with status ${response.status}`,
          parsed
        );
      }
    } catch (error) {
      caughtError = error ?? {};
    }

    clearTimeout(timeoutId);
    removeAbortListener();

    if (caughtError) {
      if (caughtError instanceof PoolSwitchError) {
        throw caughtError;
      }

      throw new PoolSwitchError("Proxy request failed", {
        cause: caughtError,
        text: caughtError && caughtError.message ? String(caughtError.message) : null
      });
    }

    return parsed;
  }

  get(path, options = {}) {
    return this.request("GET", path, options);
  }

  post(path, options = {}) {
    return this.request("POST", path, options);
  }

  put(path, options = {}) {
    return this.request("PUT", path, options);
  }

  patch(path, options = {}) {
    return this.request("PATCH", path, options);
  }

  delete(path, options = {}) {
    return this.request("DELETE", path, options);
  }
}

function normalizeHeaders(headers) {
  if (!headers) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(headers).map(([key, value]) => [
      String(key).toLowerCase(),
      String(value)
    ])
  );
}

function buildUrl(baseUrl, path, query) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${baseUrl}${normalizedPath}`);

  if (query && typeof query === "object") {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) {
        continue;
      }

      if (Array.isArray(value)) {
        for (const item of value) {
          url.searchParams.append(key, String(item));
        }
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }

  return url.toString();
}

async function parseResponse(response) {
  const headers = Object.fromEntries(response.headers.entries());
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  const text = await response.text();

  let data = text;
  if (text && (contentType.includes("application/json") || looksLikeJson(text))) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  return {
    status: response.status,
    ok: response.ok,
    headers,
    data,
    text
  };
}

function looksLikeJson(value) {
  const trimmed = value.trim();
  return trimmed.startsWith("{") || trimmed.startsWith("[");
}

module.exports = {
  PoolSwitchClient,
  PoolSwitchError
};


