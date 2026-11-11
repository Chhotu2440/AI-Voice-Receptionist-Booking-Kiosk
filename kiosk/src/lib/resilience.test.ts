import { describe, expect, it } from "vitest";

// @ts-expect-error plain JS module (the service worker source)
import { frozenClients, strategyFor } from "../sw/sw.js";
import { DAILY_UPTIME_MS, OFFLINE_RELOAD_MS, reloadReason, type ReloadInput } from "./resilience";

const NOW = 10 * DAILY_UPTIME_MS;
const base: ReloadInput = {
  now: NOW,
  bootedAt: NOW - 60_000,
  state: "IDLE",
  idleSince: NOW - 60_000,
  offlineSince: null,
  updateReady: false,
  canRecover: true,
};

describe("reloadReason", () => {
  it("never reloads mid-booking for an update or the daily refresh", () => {
    expect(reloadReason({ ...base, state: "SLOT_SELECTION", idleSince: null, updateReady: true, bootedAt: 0 })).toBeNull();
    expect(reloadReason({ ...base, updateReady: true })).toBe("update");
    expect(reloadReason({ ...base, updateReady: true, idleSince: NOW - 2_000 })).toBeNull(); // just reset
  });

  it("reloads after a long outage, but only if the page will come back", () => {
    const offline = { ...base, state: "PACKAGE_DISCOVERY", idleSince: null, offlineSince: NOW - OFFLINE_RELOAD_MS };
    expect(reloadReason(offline)).toBe("offline-too-long");
    expect(reloadReason({ ...offline, offlineSince: NOW - 60_000 })).toBeNull();
    expect(reloadReason({ ...offline, canRecover: false })).toBeNull();
  });

  it("refreshes once a day while idle", () => {
    expect(reloadReason({ ...base, bootedAt: NOW - DAILY_UPTIME_MS, idleSince: NOW - 6 * 60_000 })).toBe("daily-refresh");
    expect(reloadReason({ ...base, bootedAt: NOW - DAILY_UPTIME_MS, idleSince: NOW - 60_000 })).toBeNull();
  });
});

describe("service worker rules", () => {
  const origin = "https://kiosk.example";
  const s = (path: string, mode = "cors", method = "GET") => strategyFor(new URL(path, origin), { method, mode }, origin);

  it("never caches API or WebSocket traffic (live data, no customer data at rest)", () => {
    expect(s("/api/v1/kiosk/heartbeat", "cors", "POST")).toBe("bypass");
    expect(s("/api/v1/public/packages")).toBe("bypass");
    expect(s("/ws/kiosk")).toBe("bypass");
    expect(strategyFor(new URL("https://cdn.other/x.js"), { method: "GET", mode: "cors" }, origin)).toBe("bypass");
  });

  it("serves the app shell offline and caches build files and camera models", () => {
    expect(s("/", "navigate")).toBe("network-first-shell");
    expect(s("/assets/index-abc123.js")).toBe("cache-first");
    expect(s("/models/blaze_face_short_range.tflite")).toBe("runtime-cache");
    expect(s("/sw.js")).toBe("bypass");
  });

  it("flags only visible pages that stopped sending alive", () => {
    expect(frozenClients({ a: 1_000, b: 20_000, c: null }, 21_000, 12_000)).toEqual(["a"]);
  });
});
