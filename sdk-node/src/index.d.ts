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

export interface PoolSwitchClientOptions {
  headers?: Record<string, string>;
  timeout?: number;
  fetchImpl?: typeof fetch;
}

export declare class PoolSwitchError<T = unknown> extends Error {
  status: number | null;
  headers: Record<string, string>;
  data: T | undefined;
  text: string | null;
  cause: unknown;
}

export declare class PoolSwitchClient {
  constructor(baseUrl: string, options?: PoolSwitchClientOptions);

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


