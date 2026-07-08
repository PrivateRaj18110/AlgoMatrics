// Typed API client: bearer auth, tenant header, single-flight token refresh,
// and RFC 9457 problem-details error parsing.

import type { Tokens } from "@/types/api";

const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  errors?: unknown;

  constructor(status: number, code: string, detail: string, errors?: unknown) {
    super(detail);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.errors = errors;
  }
}

interface AuthBridge {
  getAccessToken: () => string | null;
  getOrgId: () => string | null;
  onTokens: (tokens: Tokens) => void;
  onAuthLost: () => void;
}

let bridge: AuthBridge | null = null;

export function connectAuthBridge(next: AuthBridge): void {
  bridge = next;
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  refreshPromise ??= (async () => {
    try {
      const response = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!response.ok) return false;
      const tokens = (await response.json()) as Tokens;
      bridge?.onTokens(tokens);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | boolean | undefined | null>;
  skipAuth?: boolean;
  skipOrg?: boolean;
  retryOn401?: boolean;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = "GET",
    body,
    formData,
    query,
    skipAuth = false,
    skipOrg = false,
    retryOn401 = true,
  } = options;

  let url = `${BASE}${path}`;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, String(value));
      }
    }
    const encoded = params.toString();
    if (encoded) url += `?${encoded}`;
  }

  const headers: Record<string, string> = {};
  if (!formData && body !== undefined) headers["Content-Type"] = "application/json";
  if (!skipAuth) {
    const token = bridge?.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (!skipOrg) {
      const orgId = bridge?.getOrgId();
      if (orgId) headers["X-Org-Id"] = orgId;
    }
  }

  const response = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });

  if (response.status === 401 && !skipAuth && retryOn401) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      return api<T>(path, { ...options, retryOn401: false });
    }
    bridge?.onAuthLost();
  }

  if (!response.ok) {
    let code = "http_error";
    let detail = `${response.status} ${response.statusText}`;
    let errors: unknown;
    try {
      const problem = (await response.json()) as Record<string, unknown>;
      code = typeof problem.code === "string" ? problem.code : code;
      detail = typeof problem.detail === "string" ? problem.detail : detail;
      errors = problem.errors;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(response.status, code, detail, errors);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export { BASE as API_BASE, refreshTokens };
