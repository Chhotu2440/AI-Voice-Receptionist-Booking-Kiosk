import { useEffect, useRef } from "react";

import { useKiosk } from "../store";
import type { KioskConfig } from "../types";
import { startPresence, type PresenceHandle } from "./camera";
import { DEFAULT_PRESENCE, type PresenceConfig } from "./presence";

function toPresenceConfig(c: KioskConfig): PresenceConfig {
  return {
    ...DEFAULT_PRESENCE,
    minFaceArea: c.presence_min_face_area,
    dwellMs: c.presence_dwell_ms,
    leaveMs: c.presence_leave_ms,
  };
}

/**
 * Starts on-device presence detection. A customer who stops in front of the kiosk starts a session
 * (same `start` intent as a tap); a customer who walks away mid-session triggers `onLeft`.
 * Without a camera (or if it fails) the kiosk simply stays tap-to-start (CAM-02).
 */
export function usePresence(onLeft: () => void): void {
  const config = useKiosk((s) => s.config);
  const handle = useRef<PresenceHandle | null>(null);
  const onLeftRef = useRef(onLeft);
  onLeftRef.current = onLeft;

  useEffect(() => {
    const { setCamera } = useKiosk.getState();
    if (!config.presence_enabled || !navigator.mediaDevices?.getUserMedia) {
      setCamera({ ok: null, faces: 0, present: false });
      return;
    }
    let cancelled = false;
    void startPresence(toPresenceConfig(useKiosk.getState().config), {
      onEvent: (event) => {
        const { state, allowed, send } = useKiosk.getState();
        if (event === "arrived" && state?.state === "IDLE" && allowed.includes("start")) {
          send("start", { trigger: "presence" });
        } else if (event === "left") {
          onLeftRef.current();
        }
      },
      onHealth: (ok) => setCamera({ ok }),
      onFaces: (faces, present) => setCamera({ faces, present }),
    }).then((h) => {
      if (cancelled) h.stop();
      else handle.current = h;
    });
    return () => {
      cancelled = true;
      handle.current?.stop();
      handle.current = null;
    };
  }, [config.presence_enabled]);

  useEffect(() => {
    handle.current?.setConfig(toPresenceConfig(config));
  }, [config]);
}
