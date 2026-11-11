/**
 * Kiosk self-healing (KIOSK-06). The kiosk must never sit on a blank or broken screen with nobody around.
 *
 * - Service worker (production builds): offline app shell + frozen-page watchdog (see src/sw/sw.js).
 *   The page sends "alive" every 2 s; if the main thread freezes, the worker reloads the page.
 * - Reload rules (reloadReason): a reload always lands on IDLE with an empty store, so we only reload when
 *   it can't hurt a customer and when the page will come back (the shell is cached, or the server answers).
 */

export const ALIVE_EVERY_MS = 2_000;
export const OFFLINE_RELOAD_MS = 5 * 60_000;
export const UPDATE_IDLE_MS = 10_000;
export const DAILY_UPTIME_MS = 24 * 60 * 60_000;
export const DAILY_IDLE_MS = 5 * 60_000;

export type ReloadInput = {
  now: number;
  bootedAt: number;
  state: string; // kiosk flow state
  idleSince: number | null; // when the flow last entered IDLE (null = not idle)
  offlineSince: number | null; // when the kiosk socket last went offline (null = online)
  updateReady: boolean; // a new build's service worker took control
  canRecover: boolean; // a reload will show the app again (shell cached or server reachable)
};

export type ReloadReason = "update" | "offline-too-long" | "daily-refresh";

/** Pure decision, unit-tested. */
export function reloadReason(i: ReloadInput): ReloadReason | null {
  if (!i.canRecover) return null;
  const idleFor = i.state === "IDLE" && i.idleSince !== null ? i.now - i.idleSince : 0;
  if (i.updateReady && idleFor >= UPDATE_IDLE_MS) return "update";
  // A long outage: the customer can't continue anyway. A fresh page clears any stuck connection state.
  if (i.offlineSince !== null && i.now - i.offlineSince >= OFFLINE_RELOAD_MS) return "offline-too-long";
  // Long-running browser tabs leak memory; refresh once a day while nobody is using the kiosk.
  if (i.now - i.bootedAt >= DAILY_UPTIME_MS && idleFor >= DAILY_IDLE_MS) return "daily-refresh";
  return null;
}

let updateReady = false;
export const bootedAt = Date.now();

export function isUpdateReady(): boolean {
  return updateReady;
}

/** True when a reload will render the kiosk again (cached shell) rather than a browser error page. */
export function shellIsCached(): boolean {
  return typeof navigator !== "undefined" && !!navigator.serviceWorker?.controller;
}

export function registerServiceWorker(): void {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  const hadController = !!navigator.serviceWorker.controller;
  const post = (type: "alive" | "pause") => navigator.serviceWorker.controller?.postMessage({ type });
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    // First install takes control of this page: nothing to reload. Later ones mean a new build.
    if (hadController) updateReady = true;
    post("alive"); // start the watchdog right away, not on the next tick
  });
  void navigator.serviceWorker.register("/sw.js", { type: "module", scope: "/" }).catch(() => {
    /* no SW: the kiosk still works, just without the offline shell */
  });

  window.setInterval(() => {
    if (document.visibilityState === "visible") post("alive");
  }, ALIVE_EVERY_MS);
  document.addEventListener("visibilitychange", () => post(document.visibilityState === "visible" ? "alive" : "pause"));
}

export function reloadKiosk(reason: string): void {
  // eslint-disable-next-line no-console
  console.warn("kiosk_reload", reason);
  window.location.reload();
}
