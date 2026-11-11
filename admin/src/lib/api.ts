// Thin fetch wrapper: access token in memory only (never localStorage), refresh token in an
// httpOnly SameSite=Strict cookie scoped to /api/v1/auth. A 401 triggers one silent refresh + retry.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onSignedOut: () => void = () => {};

export function setSignedOutHandler(fn: () => void) {
  onSignedOut = fn;
}

export function hasToken() {
  return accessToken !== null;
}

async function parseError(r: Response): Promise<ApiError> {
  let body: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } = {};
  try {
    body = await r.json();
  } catch {
    /* non-JSON error */
  }
  const e = body.error ?? {};
  return new ApiError(r.status, e.code ?? `HTTP_${r.status}`, e.message ?? r.statusText, e.details ?? {});
}

export async function refresh(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const r = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin" });
      if (!r.ok) {
        accessToken = null;
        return false;
      }
      accessToken = (await r.json()).access_token as string;
      return true;
    } catch {
      return false;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

export async function login(email: string, password: string): Promise<void> {
  const r = await fetch("/api/v1/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw await parseError(r);
  accessToken = (await r.json()).access_token as string;
}

export async function logout(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin" });
  } finally {
    accessToken = null;
  }
}

type Opts = { method?: string; body?: unknown; headers?: Record<string, string> };

export async function api<T>(path: string, opts: Opts = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch(`/api/v1${path}`, {
    method: opts.method ?? "GET",
    headers,
    credentials: "same-origin",
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  if (r.status === 401 && retry) {
    if (await refresh()) return api<T>(path, opts, false);
    onSignedOut();
  }
  if (!r.ok) throw await parseError(r);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export function idempotencyKey(): string {
  return crypto.randomUUID();
}

export function qs(params: Record<string, string | number | string[] | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, x));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}
