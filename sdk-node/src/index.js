"use strict";

const DEFAULT_RETRYABLE_METHODS = ["GET", "HEAD", "OPTIONS", "DELETE", "POST"];
const QUOTA_HINTS = ["quota", "insufficient_quota", "quota_exceeded", "credits exhausted"];
const RATE_LIMIT_HINTS = ["rate limit", "too many requests", "slow down", "throttled"];

class PoolSwitchError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "PoolSwitchError";
    this.status = details.status ?? null;
    this.headers = details.headers ?? {};
    this.data = details.data;
    this.text = details.text ?? null;
    this.reason = details.reason ?? "";
    this.cause = details.cause;
  }
}

class PoolSwitchProxyClient {
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

class PoolSwitchClient {
  constructor(options = {}) {
    if (!isPlainObject(options)) {
      throw new TypeError("PoolSwitchClient options must be an object");
    }
    if (!options.upstreamBaseUrl || typeof options.upstreamBaseUrl !== "string") {
      throw new TypeError("upstreamBaseUrl must be a non-empty string");
    }
    if (!Array.isArray(options.keys) || options.keys.length === 0) {
      throw new TypeError("keys must be a non-empty array");
    }

    this.upstreamBaseUrl = options.upstreamBaseUrl.replace(/\/+$/, "");
    this.authHeaderName = options.authHeaderName ?? "Authorization";
    this.authScheme = Object.prototype.hasOwnProperty.call(options, "authScheme") ? options.authScheme : "Bearer";
    this.strategy = options.strategy ?? "quota_failover";
    this.retryAttempts = options.retryAttempts ?? 3;
    this.cooldownSeconds = options.cooldownSeconds ?? 3600;
    this.timeout = options.timeout ?? 30000;
    this.rateLimitPerSecond = Math.max(options.rateLimitPerSecond ?? 50, 0.1);
    this.retryableMethods = (options.retryableMethods ?? DEFAULT_RETRYABLE_METHODS).map((item) =>
      String(item).toUpperCase()
    );
    this.defaultHeaders = normalizeHeaders(options.headers);
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
    this.random = options.random ?? Math.random;
    this.sleep = options.sleep ?? defaultSleep;
    this.maxRequests = Math.max(1, Math.ceil(this.rateLimitPerSecond));
    this.requestTimestamps = [];
    this.roundRobinIndex = 0;
    this.keyDefinitions = normalizeEmbeddedKeys(options.keys);
    this.states = new Map(
      this.keyDefinitions.map((definition) => [
        definition.id,
        {
          keyId: definition.id,
          totalRequests: 0,
          errorCount: 0,
          failoverCount: 0,
          estimatedRemainingQuota: definition.monthlyQuota ?? null,
          lastUsedAt: null,
          cooldownUntil: null,
          consecutiveRateLimits: 0
        }
      ])
    );

    if (typeof this.fetchImpl !== "function") {
      throw new TypeError("A fetch implementation is required");
    }
    if (!["round_robin", "least_used", "random", "quota_failover"].includes(this.strategy)) {
      throw new TypeError("strategy must be one of round_robin, least_used, random, or quota_failover");
    }
  }

  async request(method, path, options = {}) {
    const methodUpper = String(method).toUpperCase();
    const retryableMethod = this.retryableMethods.includes(methodUpper);
    const excludedKeys = new Set();
    let attempts = 0;

    while (true) {
      attempts += 1;
      const record = this.acquireKey(excludedKeys);

      await this.acquireRateLimit();

      let parsed;
      try {
        parsed = await this.performFetch(methodUpper, path, options, record.definition);
      } catch (error) {
        this.recordTransientError(record.definition.id, "network_error");
        excludedKeys.add(record.definition.id);
        this.recordFailover(record.definition.id);
        const decision = retryDecision({
          attemptNumber: attempts,
          retryAttempts: this.retryAttempts,
          retryable: retryableMethod,
          reason: "network_error",
          random: this.random
        });
        if (decision.shouldRetry) {
          await this.sleep(decision.delaySeconds);
          continue;
        }
        throw new PoolSwitchError("Upstream request failed", {
          reason: "network_error",
          cause: error,
          text: error && error.message ? String(error.message) : null
        });
      }

      const classification = classifyParsedResponse(parsed);
      if (classification.quotaExceeded) {
        this.markKeyQuotaExhausted(record.definition.id, classification.reason);
        excludedKeys.add(record.definition.id);
        this.recordFailover(record.definition.id);
        const decision = retryDecision({
          attemptNumber: attempts,
          retryAttempts: this.retryAttempts,
          retryable: retryableMethod,
          reason: classification.reason,
          random: this.random
        });
        if (decision.shouldRetry) {
          await this.sleep(decision.delaySeconds);
          continue;
        }
        return finalizeEmbeddedResponse(parsed, classification.reason);
      }

      if (classification.shouldRetry) {
        this.recordTransientError(record.definition.id, classification.reason);
        excludedKeys.add(record.definition.id);
        this.recordFailover(record.definition.id);
        const decision = retryDecision({
          attemptNumber: attempts,
          retryAttempts: this.retryAttempts,
          retryable: retryableMethod,
          reason: classification.reason,
          random: this.random
        });
        if (decision.shouldRetry) {
          await this.sleep(decision.delaySeconds);
          continue;
        }
        return finalizeEmbeddedResponse(parsed, classification.reason);
      }

      this.recordSuccess(record.definition.id, extractRemainingQuota(parsed));
      return finalizeEmbeddedResponse(parsed);
    }
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

  status() {
    return {
      strategy: this.strategy,
      upstreamBaseUrl: this.upstreamBaseUrl,
      keys: this.keyDefinitions.map((definition) => {
        const state = this.states.get(definition.id);
        return {
          id: definition.id,
          totalRequests: state.totalRequests,
          errorCount: state.errorCount,
          failoverCount: state.failoverCount,
          estimatedRemainingQuota: state.estimatedRemainingQuota,
          lastUsedAt: state.lastUsedAt,
          cooldownUntil: state.cooldownUntil
        };
      })
    };
  }

  acquireKey(excludedKeys = new Set()) {
    const now = Date.now();
    const candidates = this.keyDefinitions
      .map((definition) => ({ definition, state: this.states.get(definition.id) }))
      .filter((record) => !excludedKeys.has(record.definition.id) && !isInCooldown(record.state, now));

    if (candidates.length === 0) {
      throw new PoolSwitchError("No healthy API keys available", {
        reason: "no_healthy_keys",
        text: "All API keys are in cooldown or unavailable."
      });
    }

    return chooseRecord(this.strategy, candidates, {
      nextRandom: () => this.random(),
      nextRoundRobinIndex: () => this.roundRobinIndex++
    });
  }

  async acquireRateLimit() {
    const now = Date.now();
    const windowStart = now - 1000;
    this.requestTimestamps = this.requestTimestamps.filter((timestamp) => timestamp >= windowStart);
    if (this.requestTimestamps.length >= this.maxRequests) {
      const delay = this.requestTimestamps[0] - windowStart;
      await this.sleep(Math.max(delay, 1));
      return this.acquireRateLimit();
    }
    this.requestTimestamps.push(Date.now());
  }

  async performFetch(method, path, options, definition) {
    const url = buildUrl(this.upstreamBaseUrl, path, options.query);
    const headers = this.requestHeaders(options.headers, definition);
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

    try {
      const hasJson = Object.prototype.hasOwnProperty.call(options, "json");
      const body = hasJson ? JSON.stringify(options.json) : options.body;

      if (hasJson && headers["content-type"] === undefined) {
        headers["content-type"] = "application/json";
      }

      const response = await this.fetchImpl(url, {
        method,
        headers,
        body,
        signal: controller.signal
      });

      return await parseResponse(response);
    } finally {
      clearTimeout(timeoutId);
      removeAbortListener();
    }
  }

  requestHeaders(headers, definition) {
    const merged = {
      ...this.defaultHeaders,
      ...normalizeHeaders(headers)
    };
    const authHeader = this.authHeaderName.toLowerCase();
    const sanitized = Object.fromEntries(
      Object.entries(merged).filter(([key]) => key.toLowerCase() !== authHeader)
    );
    sanitized[this.authHeaderName] =
      this.authScheme === null || this.authScheme === undefined || this.authScheme === ""
        ? definition.value
        : `${this.authScheme} ${definition.value}`;
    return sanitized;
  }

  recordSuccess(keyId, remainingQuota) {
    const state = this.states.get(keyId);
    state.totalRequests += 1;
    state.lastUsedAt = new Date().toISOString();
    state.consecutiveRateLimits = 0;
    state.cooldownUntil = null;
    if (remainingQuota !== null) {
      state.estimatedRemainingQuota = remainingQuota;
    }
  }

  recordTransientError(keyId, reason) {
    const state = this.states.get(keyId);
    state.errorCount += 1;
    state.lastUsedAt = new Date().toISOString();
    if (reason === "rate_limited") {
      state.consecutiveRateLimits += 1;
    }
  }

  markKeyQuotaExhausted(keyId) {
    const state = this.states.get(keyId);
    state.errorCount += 1;
    state.consecutiveRateLimits += 1;
    state.cooldownUntil = new Date(Date.now() + this.cooldownSeconds * 1000).toISOString();
    state.lastUsedAt = new Date().toISOString();
    if (state.estimatedRemainingQuota === null || state.estimatedRemainingQuota > 0) {
      state.estimatedRemainingQuota = 0;
    }
  }

  recordFailover(keyId) {
    const state = this.states.get(keyId);
    state.failoverCount += 1;
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

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function normalizeEmbeddedKeys(keys) {
  return keys.map((value, index) => {
    if (typeof value === "string") {
      return { id: `key-${index + 1}`, value, monthlyQuota: null, metadata: {} };
    }
    if (!isPlainObject(value) || typeof value.value !== "string" || !value.value) {
      throw new TypeError("each key must be a string or an object with a value field");
    }
    return {
      id: typeof value.id === "string" && value.id ? value.id : `key-${index + 1}`,
      value: value.value,
      monthlyQuota: typeof value.monthlyQuota === "number" ? value.monthlyQuota : null,
      metadata: isPlainObject(value.metadata) ? value.metadata : {}
    };
  });
}

function chooseRecord(strategy, candidates, helpers) {
  if (strategy === "round_robin") {
    return candidates[helpers.nextRoundRobinIndex() % candidates.length];
  }
  if (strategy === "least_used") {
    return minBy(candidates, (candidate) => [
      candidate.state.totalRequests,
      candidate.state.errorCount,
      timestampOrMinimum(candidate.state.lastUsedAt)
    ]);
  }
  if (strategy === "random") {
    const index = Math.floor(helpers.nextRandom() * candidates.length);
    return candidates[Math.min(index, candidates.length - 1)];
  }
  return minBy(candidates, (candidate) => [
    candidate.state.estimatedRemainingQuota === null ? 1 : 0,
    -(candidate.state.estimatedRemainingQuota ?? 0),
    candidate.state.consecutiveRateLimits,
    candidate.state.errorCount,
    candidate.state.totalRequests,
    timestampOrMinimum(candidate.state.lastUsedAt)
  ]);
}

function minBy(values, selector) {
  return values.reduce((best, current) => {
    if (!best) {
      return current;
    }
    return compareTuple(selector(current), selector(best)) < 0 ? current : best;
  }, null);
}

function compareTuple(left, right) {
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] < right[index]) {
      return -1;
    }
    if (left[index] > right[index]) {
      return 1;
    }
  }
  return 0;
}

function timestampOrMinimum(value) {
  return value ? Date.parse(value) : 0;
}

function isInCooldown(state, now) {
  return state.cooldownUntil !== null && Date.parse(state.cooldownUntil) > now;
}

function flattenMessages(payload) {
  if (payload === null || payload === undefined) {
    return "";
  }
  if (typeof payload === "string") {
    return payload.toLowerCase();
  }
  if (Array.isArray(payload)) {
    return payload.map((item) => flattenMessages(item)).join(" ");
  }
  if (typeof payload === "object") {
    return Object.values(payload)
      .map((item) => flattenMessages(item))
      .join(" ");
  }
  return String(payload).toLowerCase();
}

function classifyParsedResponse(parsed) {
  const messageBlob = flattenMessages(parsed.data || parsed.text);
  const retryAfter = parsed.headers["retry-after"];

  if (parsed.status === 429) {
    if (QUOTA_HINTS.some((hint) => messageBlob.includes(hint))) {
      return { shouldRetry: true, quotaExceeded: true, reason: "quota_exceeded" };
    }
    if (RATE_LIMIT_HINTS.some((hint) => messageBlob.includes(hint))) {
      return { shouldRetry: true, quotaExceeded: false, reason: "rate_limited" };
    }
    return { shouldRetry: true, quotaExceeded: false, reason: "rate_limited" };
  }

  if ((parsed.status === 401 || parsed.status === 403) && QUOTA_HINTS.some((hint) => messageBlob.includes(hint))) {
    return { shouldRetry: false, quotaExceeded: true, reason: "quota_exceeded" };
  }

  if (retryAfter && parsed.status >= 500) {
    return { shouldRetry: true, quotaExceeded: false, reason: "upstream_retry_after" };
  }

  return { shouldRetry: false, quotaExceeded: false, reason: "ok" };
}

function extractRemainingQuota(parsed) {
  for (const headerName of ["x-ratelimit-remaining", "x-remaining-quota", "x-usage-remaining"]) {
    const value = parsed.headers[headerName];
    if (value === undefined) {
      continue;
    }
    const converted = Number.parseInt(Number.parseFloat(value), 10);
    if (!Number.isNaN(converted)) {
      return converted;
    }
  }

  const usage = isPlainObject(parsed.data) ? parsed.data.usage : null;
  const remaining = isPlainObject(usage) ? usage.remaining_quota : null;
  return Number.isInteger(remaining) ? remaining : null;
}

function retryDecision({ attemptNumber, retryAttempts, retryable, reason, random }) {
  if (!retryable || attemptNumber >= retryAttempts) {
    return { shouldRetry: false, delaySeconds: 0, reason };
  }
  const normalizedAttempt = Math.max(attemptNumber, 1);
  const delay = Math.min(0.25 * (2 ** (normalizedAttempt - 1)), 5);
  const jitter = delay * 0.2 * random();
  return { shouldRetry: true, delaySeconds: delay + jitter, reason };
}

function finalizeEmbeddedResponse(parsed, reason = "") {
  if (parsed.ok) {
    return parsed.data;
  }
  throw new PoolSwitchError("Upstream returned an error", {
    status: parsed.status,
    headers: parsed.headers,
    data: parsed.data,
    text: parsed.text,
    reason
  });
}

function defaultSleep(delaySeconds) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, delaySeconds * 1000)));
}

module.exports = {
  PoolSwitchClient,
  PoolSwitchError,
  PoolSwitchProxyClient
};
