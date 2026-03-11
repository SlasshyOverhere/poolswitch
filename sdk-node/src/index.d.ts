export interface PoolSwitchResponse<T = unknown> {
  status: number;
  ok: boolean;
  headers: Record<string, string>;
  data: T;
  text: string;
}

export interface PoolSwitchRequestOptions {
  headers?: Record<string, string>;
  json?: unknown;
  body?: BodyInit | null;
  query?: Record<string, string | number | boolean | Array<string | number | boolean> | null | undefined>;
  timeout?: number;
  signal?: AbortSignal;
}

export interface PoolSwitchProxyClientOptions {
  headers?: Record<string, string>;
  timeout?: number;
  fetchImpl?: typeof fetch;
}

export interface EmbeddedPoolSwitchKey {
  id?: string;
  value: string;
  monthlyQuota?: number;
  metadata?: Record<string, unknown>;
}

export interface EmbeddedPoolSwitchClientOptions {
  upstreamBaseUrl: string;
  keys: Array<string | EmbeddedPoolSwitchKey>;
  authHeaderName?: string;
  authScheme?: string | null;
  strategy?: "round_robin" | "least_used" | "random" | "quota_failover";
  retryAttempts?: number;
  cooldownSeconds?: number;
  timeout?: number;
  rateLimitPerSecond?: number;
  retryableMethods?: string[];
  headers?: Record<string, string>;
  fetchImpl?: typeof fetch;
}

export interface EmbeddedPoolSwitchKeyStatus {
  id: string;
  totalRequests: number;
  errorCount: number;
  failoverCount: number;
  estimatedRemainingQuota: number | null;
  lastUsedAt: string | null;
  cooldownUntil: string | null;
}

export interface EmbeddedPoolSwitchStatus {
  strategy: string;
  upstreamBaseUrl: string;
  keys: EmbeddedPoolSwitchKeyStatus[];
}

export declare class PoolSwitchError<T = unknown> extends Error {
  status: number | null;
  headers: Record<string, string>;
  data: T | undefined;
  text: string | null;
  reason: string;
  cause: unknown;
}

export declare class PoolSwitchProxyClient {
  constructor(baseUrl: string, options?: PoolSwitchProxyClientOptions);

  request<T = unknown>(
    method: string,
    path: string,
    options?: PoolSwitchRequestOptions
  ): Promise<PoolSwitchResponse<T>>;

  get<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<PoolSwitchResponse<T>>;
  post<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<PoolSwitchResponse<T>>;
  put<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<PoolSwitchResponse<T>>;
  patch<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<PoolSwitchResponse<T>>;
  delete<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<PoolSwitchResponse<T>>;
}

export declare class PoolSwitchClient {
  constructor(options: EmbeddedPoolSwitchClientOptions);

  request<T = unknown>(
    method: string,
    path: string,
    options?: PoolSwitchRequestOptions
  ): Promise<T | string>;

  get<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<T | string>;
  post<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<T | string>;
  put<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<T | string>;
  patch<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<T | string>;
  delete<T = unknown>(path: string, options?: PoolSwitchRequestOptions): Promise<T | string>;

  status(): EmbeddedPoolSwitchStatus;
}
