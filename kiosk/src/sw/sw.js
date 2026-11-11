/* Kiosk service worker (KIOSK-06): offline app shell + frozen-page watchdog.
 *
 * Built into dist/sw.js by the `kioskServiceWorker` Vite plugin (vite.config.ts), which fills in BUILD_ID and
 * PRECACHE with the build's hashed files. Registered as a module worker, production only.
 *
 * Caching rules (see strategyFor):
 *   - /api/* and /ws/* are NEVER cached: booking data is always live, and no customer data is stored.
 *   - Page loads: network first; offline -> the cached app shell (the app then shows "Reconnecting").
 *   - Hashed build files (/assets/*): cache first (the name changes when the content changes).
 *   - Camera model + wasm (/models/*, /mediapipe/*): cached on first use, so presence keeps working offline.
 *
 * Watchdog: the page posts {type:"alive"} every 2 s while visible. If a visible page goes silent for
 * WATCHDOG_MS (main thread frozen), the worker reloads it. Reload always starts the kiosk at IDLE.
 */

export const BUILD_ID = "__BUILD_ID__";
/** @type {string[]} */
export const PRECACHE = /*__PRECACHE__*/ [];
export const WATCHDOG_MS = 12_000;

const SHELL_CACHE = `plt-kiosk-shell-${BUILD_ID}`;
const RUNTIME_CACHE = "plt-kiosk-runtime-v1";

/**
 * @param {URL} url
 * @param {{ method: string, mode: string }} req
 * @returns {"bypass" | "network-first-shell" | "cache-first" | "runtime-cache"}
 */
export function strategyFor(url, req, origin) {
  if (req.method !== "GET" || url.origin !== origin) return "bypass";
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) return "bypass";
  if (url.pathname === "/sw.js") return "bypass";
  if (req.mode === "navigate") return "network-first-shell";
  if (url.pathname.startsWith("/assets/")) return "cache-first";
  if (url.pathname.startsWith("/models/") || url.pathname.startsWith("/mediapipe/")) return "runtime-cache";
  return "bypass";
}

/** Decide which clients froze. Pure, for tests. */
export function frozenClients(lastAlive, now, timeoutMs = WATCHDOG_MS) {
  return Object.entries(lastAlive)
    .filter(([, at]) => at !== null && now - at > timeoutMs)
    .map(([id]) => id);
}

const sw = /** @type {any} */ (typeof self !== "undefined" && "registration" in self ? self : null);

if (sw) {
  /** @type {Record<string, number | null>} client id -> last alive time (null = hidden/paused) */
  const lastAlive = {};
  let timer = 0;

  sw.addEventListener("install", (event) => {
    event.waitUntil(
      caches
        .open(SHELL_CACHE)
        .then((c) => c.addAll(["/", ...PRECACHE]))
        .then(() => sw.skipWaiting()),
    );
  });

  sw.addEventListener("activate", (event) => {
    event.waitUntil(
      caches
        .keys()
        .then((keys) => Promise.all(keys.filter((k) => k.startsWith("plt-kiosk-shell-") && k !== SHELL_CACHE).map((k) => caches.delete(k))))
        .then(() => sw.clients.claim()),
    );
  });

  sw.addEventListener("fetch", (event) => {
    const req = event.request;
    const url = new URL(req.url);
    const strategy = strategyFor(url, req, sw.location.origin);
    if (strategy === "bypass") return;
    if (strategy === "network-first-shell") {
      event.respondWith(
        fetch(req).catch(
          async () => (await caches.match("/", { cacheName: SHELL_CACHE, ignoreVary: true })) ?? Response.error(),
        ),
      );
      return;
    }
    const cacheName = strategy === "cache-first" ? SHELL_CACHE : RUNTIME_CACHE;
    event.respondWith(
      caches.open(cacheName).then(async (cache) => {
        // ignoreVary: servers send "Vary: Origin"; module scripts carry an Origin header the precache request lacked.
        const hit = await cache.match(req, { ignoreVary: true });
        if (hit) return hit;
        const res = await fetch(req);
        if (res.ok) await cache.put(req, res.clone());
        return res;
      }),
    );
  });

  const check = async () => {
    timer = 0;
    const now = Date.now();
    for (const id of frozenClients(lastAlive, now)) {
      delete lastAlive[id];
      const client = await sw.clients.get(id);
      if (client && "navigate" in client) {
        try {
          await client.navigate(client.url);
        } catch {
          /* client gone */
        }
      }
    }
    if (Object.values(lastAlive).some((v) => v !== null)) timer = setTimeout(check, 2_000);
  };

  sw.addEventListener("message", (event) => {
    const id = event.source && event.source.id;
    if (!id || !event.data) return;
    if (event.data.type === "alive") lastAlive[id] = Date.now();
    else if (event.data.type === "pause") lastAlive[id] = null; // hidden tab: timers are throttled
    if (!timer) timer = setTimeout(check, 2_000);
  });
}
