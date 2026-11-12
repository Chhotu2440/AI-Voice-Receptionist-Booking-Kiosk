import { useEffect, useRef } from "react";

import { audioLevel, displayableCaption, useKiosk } from "../store";
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
    let caption = "";
    let newTurn = true;
    void getToken().then((token) => {
      if (cancelled) return;
      const v = new VoiceSession(token, {
        onStatus: (status) => {
          useKiosk.getState().setVoice({ status });
          if (status === "speaking" || status === "thinking") useKiosk.getState().touchActivity();
          if (status === "listening" || status === "thinking") newTurn = true;
        },
        onCaption: (c) => {
          const st = useKiosk.getState();
          st.touchActivity();
          if (c.role !== "assistant") return; // the customer's own words are never put on the public screen
          // Providers stream the transcript in pieces: join them per reply; a final transcript replaces all.
          if (c.final) caption = c.text;
          else if (newTurn) caption = c.text;
          else caption += c.text;
          newTurn = false;
          const text = caption.trim();
          // Only English or Hindi script is shown.
          if (text && displayableCaption(text)) st.setVoice({ caption: text.length > 180 ? "…" + text.slice(-180) : text });
        },
        onOutputLevel: (level) => {
          audioLevel.output = level;
        },
        onUserSpeaking: (speaking) => {
          useKiosk.getState().setVoice({ userSpeaking: speaking });
          if (speaking) useKiosk.getState().touchActivity();
        },
      });
      v.muted = useKiosk.getState().voice.muted;
      v.setVolume(useKiosk.getState().config.volume);
      session.current = v;
      v.start();
    });
    // The mic toggle lives in the store; apply changes to the running conversation.
    const unsubscribe = useKiosk.subscribe((st, prev) => {
      if (st.voice.muted !== prev.voice.muted) session.current?.setMuted(st.voice.muted);
      if (st.config.volume !== prev.config.volume) session.current?.setVolume(st.config.volume);
    });
    return () => {
      cancelled = true;
      unsubscribe();
      session.current?.stop();
      session.current = null;
    };
  }, [enabled, online, sessionId, getToken]);
}
