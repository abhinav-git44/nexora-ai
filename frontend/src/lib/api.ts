/* Typed fetch wrapper. Access token lives in memory only; the refresh token is an httpOnly cookie scoped to /api/auth. */
export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let accessToken: string | null = null;
let orgId: string | null = typeof window !== "undefined" ? safeGet("nx_org") : null;
let refreshing: Promise<boolean> | null = null;
let onUnauthorized: (() => void) | null = null;

function safeGet(k: string) {
  try {
    return window.localStorage.getItem(k);
  } catch {
    return null;
  }
}
function safeSet(k: string, v: string | null) {
  try {
    if (v === null) window.localStorage.removeItem(k);
    else window.localStorage.setItem(k, v);
  } catch {
    /* storage unavailable */
  }
}

export const session = {
  setToken(t: string | null) {
    accessToken = t;
    // Non-sensitive hint so signed-out visitors don't trigger a refresh request (and a 401) on every page load.
    safeSet("nx_signed_in", t ? "1" : null);
  },
  hasHint: () => typeof window !== "undefined" && safeGet("nx_signed_in") === "1",
  getToken: () => accessToken,
  setOrg(id: string | null) {
    orgId = id;
    safeSet("nx_org", id);
  },
  getOrg: () => orgId,
  onUnauthorized(fn: () => void) {
    onUnauthorized = fn;
  },
};

export async function refreshToken(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const r = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
        if (!r.ok) {
          safeSet("nx_signed_in", null);
          return false;
        }
        const d = await r.json();
        accessToken = d.access_token;
        safeSet("nx_signed_in", "1");
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

type Opts = { method?: string; body?: unknown; form?: FormData; raw?: boolean; noOrg?: boolean; signal?: AbortSignal };

export async function api<T = unknown>(path: string, opts: Opts = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  if (orgId && !opts.noOrg) headers["X-Org-Id"] = orgId;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`/api${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body, credentials: "same-origin", signal: opts.signal });
  if (res.status === 401 && !retried && !path.startsWith("/auth/login") && !path.startsWith("/auth/register")) {
    if (await refreshToken()) return api<T>(path, opts, true);
    onUnauthorized?.();
  }
  if (!res.ok) {
    let err: { code?: string; message?: string; details?: Record<string, unknown> } = {};
    try {
      err = (await res.json()).error || {};
    } catch {
      /* non-JSON */
    }
    throw new ApiError(res.status, err.code || "error", err.message || `Request failed (${res.status})`, err.details || {});
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function download(path: string, filename: string) {
  const res = await api<Response>(path, { raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const fetcher = <T,>(path: string) => api<T>(path);
