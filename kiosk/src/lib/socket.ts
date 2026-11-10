import type { ServerMessage } from "../types";

type Listener = (msg: ServerMessage) => void;
type StatusListener = (status: "connecting" | "online" | "offline") => void;

/**
 * WebSocket client for /ws/kiosk.
 * - Authenticates with the device JWT in the first frame (never in the URL).
 * - Reconnects with backoff. It resumes only the session id this page instance saw; after a reload the id
 *   is gone, so the server ends the old session and nobody sees the previous customer's details.
 */
export class KioskSocket {
  private ws: WebSocket | null = null;
  private retry = 0;
  private closed = false;
  private pingTimer: number | undefined;
  private seq = 0;
  resumeSessionId: string | null = null;

  constructor(
    private getToken: () => Promise<string>,
    private onMessage: Listener,
    private onStatus: StatusListener,
  ) {}

  async connect(): Promise<void> {
    this.onStatus("connecting");
    let token: string;
    try {
      token = await this.getToken();
    } catch {
      this.scheduleReconnect();
      return;
    }
    if (this.closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/kiosk`);
    this.ws = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "auth", token, resume_session_id: this.resumeSessionId }));
      this.retry = 0;
      this.onStatus("online");
      this.pingTimer = window.setInterval(() => this.raw({ type: "ping" }), 20_000);
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as ServerMessage;
        if (msg.type === "state") this.resumeSessionId = msg.state.session_id;
        this.onMessage(msg);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      window.clearInterval(this.pingTimer);
      if (this.ws === ws) this.ws = null;
      if (!this.closed) {
        this.onStatus("offline");
        this.scheduleReconnect();
      }
    };
  }

  private scheduleReconnect(): void {
    if (this.closed) return;
    const delay = Math.min(10_000, 500 * 2 ** this.retry++);
    window.setTimeout(() => void this.connect(), delay);
  }

  private raw(obj: unknown): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
      return true;
    }
    return false;
  }

  intent(name: string, payload: Record<string, unknown> = {}): string | null {
    const id = String(++this.seq);
    return this.raw({ type: "intent", id, name, payload }) ? id : null;
  }

  close(): void {
    this.closed = true;
    window.clearInterval(this.pingTimer);
    this.ws?.close();
  }
}
