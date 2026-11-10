import { useEffect, useRef } from "react";

import { useKiosk } from "../store";
import { VoiceSession } from "./voice";

/**
 * Runs one voice conversation per kiosk session when voice is enabled for this kiosk (admin config).
 * The conversation starts when a session starts (presence or tap) and ends when the kiosk returns to idle.
 * If voice is unavailable (no key, provider outage, no microphone) the touch flow is unaffected.
 */
export function useVoice(getToken: () => Promise<string>): void {
  const enabled = useKiosk((s) => s.config.voice_enabled);
  const online = useKiosk((s) => s.conn === "online");
  const sessionId = useKiosk((s) => s.state?.session_id ?? null);
  const session = useRef<VoiceSession | null>(null);

  useEffect(() => {
    const { setVoice } = useKiosk.getState();
    if (!enabled || !online || !sessionId) {
      session.current?.stop();
      session.current = null;
      setVoice({ status: "off", caption: null });
      return;
    }
    let cancelled = false;
    void getToken().then((token) => {
      if (cancelled) return;
      const v = new VoiceSession(token, {
        onStatus: (status) => useKiosk.getState().setVoice({ status }),
        onCaption: (c) => useKiosk.getState().setVoice({ caption: { role: c.role, text: c.text } }),
      });
      v.muted = useKiosk.getState().voice.muted;
      session.current = v;
      v.start();
    });
    // The mic toggle lives in the store; apply changes to the running conversation.
    const unsubscribe = useKiosk.subscribe((st, prev) => {
      if (st.voice.muted !== prev.voice.muted) session.current?.setMuted(st.voice.muted);
    });
    return () => {
      cancelled = true;
      unsubscribe();
      session.current?.stop();
      session.current = null;
    };
  }, [enabled, online, sessionId, getToken]);
}
