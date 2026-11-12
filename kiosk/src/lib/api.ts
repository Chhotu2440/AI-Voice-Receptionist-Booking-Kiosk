import type { KioskConfig } from "../types";

// Device credentials are long-lived and live in localStorage (the kiosk browser profile is dedicated and
// locked down). Customer data is NEVER written to storage; it only exists in the live session state.
const CREDS_KEY = "plt.kiosk.device";
export const APP_VERSION: string = __APP_VERSION__;

export interface DeviceCreds {
  device_id: string;
  device_secret: string;
  name: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function post<T>(path: string, body: unknown, token?: string): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, data?.error?.code ?? "HTTP_ERROR", data?.error?.message ?? res.statusText);
  }
  return data as T;
}

export function loadCreds(): DeviceCreds | null {
  try {
    const raw = localStorage.getItem(CREDS_KEY);
    return raw ? (JSON.parse(raw) as DeviceCreds) : null;
  } catch {
    return null;
  }
}

export function saveCreds(creds: DeviceCreds | null): void {
  try {
    if (creds) localStorage.setItem(CREDS_KEY, JSON.stringify(creds));
    else localStorage.removeItem(CREDS_KEY);
  } catch {
    /* storage unavailable: pairing will be needed again after reload */
  }
}

export async function pairDevice(code: string): Promise<DeviceCreds> {
  const creds = await post<DeviceCreds>("/kiosk/register", { pairing_code: code });
  saveCreds(creds);
  return creds;
}

export async function deviceToken(creds: DeviceCreds): Promise<string> {
  const r = await post<{ access_token: string }>("/kiosk/token", {
    device_id: creds.device_id,
    device_secret: creds.device_secret,
  });
  return r.access_token;
}

export async function heartbeat(token: string, health: Record<string, boolean | undefined>): Promise<KioskConfig> {
  const r = await post<{ config: KioskConfig }>("/kiosk/heartbeat", { app_version: APP_VERSION, ...health }, token);
  return r.config;
}
