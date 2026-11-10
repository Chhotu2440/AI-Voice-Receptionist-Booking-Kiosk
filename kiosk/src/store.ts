import { create } from "zustand";

import { STRINGS } from "./i18n";
import type { KioskSocket } from "./lib/socket";
import type { VoiceStatus } from "./lib/voice";
import type { KioskConfig, KioskState, Lang, ServerMessage } from "./types";

type Conn = "connecting" | "online" | "offline";

interface KioskStore {
  conn: Conn;
  state: KioskState | null;
  allowed: string[];
  pending: string | null; // intent id awaiting a reply (buttons show busy, double taps are ignored)
  toast: { code: string; message: string; for?: string | null } | null;
  config: KioskConfig;
  socket: KioskSocket | null;
  camera: { ok: boolean | null; faces: number; present: boolean };
  voice: { status: VoiceStatus; caption: { role: string; text: string } | null; muted: boolean };
  setVoice: (v: Partial<KioskStore["voice"]>) => void;
  setCamera: (c: Partial<KioskStore["camera"]>) => void;
  setSocket: (s: KioskSocket | null) => void;
  setConn: (c: Conn) => void;
  setConfig: (c: KioskConfig) => void;
  receive: (msg: ServerMessage) => void;
  send: (name: string, payload?: Record<string, unknown>) => void;
  clearToast: () => void;
}

export const DEFAULT_CONFIG: KioskConfig = {
  idle_timeout_s: 60,
  success_reset_s: 20,
  voice_enabled: false,
  volume: 70,
  assistant_name: "Zara",
  presence_enabled: true,
  presence_min_face_area: 0.02,
  presence_dwell_ms: 1500,
  presence_leave_ms: 15000,
  presence_debug: false,
};

export const useKiosk = create<KioskStore>((set, get) => ({
  conn: "connecting",
  state: null,
  allowed: [],
  pending: null,
  toast: null,
  config: DEFAULT_CONFIG,
  socket: null,
  camera: { ok: null, faces: 0, present: false },
  voice: { status: "off", caption: null, muted: false },
  setVoice: (v) => set({ voice: { ...get().voice, ...v } }),
  setCamera: (c) => set({ camera: { ...get().camera, ...c } }),
  setSocket: (socket) => set({ socket }),
  setConn: (conn) => set(conn === "online" ? { conn } : { conn, pending: null }),
  setConfig: (config) => set({ config: { ...DEFAULT_CONFIG, ...config } }),
  receive: (msg) => {
    if (msg.type === "state") {
      const pending = get().pending;
      set({
        state: msg.state,
        allowed: msg.allowed,
        pending: msg.in_reply_to && msg.in_reply_to === pending ? null : pending,
        // Keep a transport-level error that belongs to this reply; otherwise show the state's own error.
        toast: msg.state.error ?? (get().toast?.for === msg.in_reply_to ? get().toast : null),
      });
    } else if (msg.type === "error") {
      set({ toast: { ...msg.error, for: msg.in_reply_to } });
    }
  },
  send: (name, payload = {}) => {
    const { socket, pending, allowed } = get();
    if (!socket || pending) return;
    if (!allowed.includes(name)) return;
    const id = socket.intent(name, payload);
    if (id) set({ pending: id, toast: null });
  },
  clearToast: () => set({ toast: null }),
}));

export function useT() {
  const lang: Lang = useKiosk((s) => s.state?.language ?? "en");
  return { t: STRINGS[lang], lang };
}
