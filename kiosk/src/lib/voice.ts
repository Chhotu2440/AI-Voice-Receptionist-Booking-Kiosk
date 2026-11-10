import captureUrl from "./worklets/capture.worklet.js?url";
import playbackUrl from "./worklets/playback.worklet.js?url";

export type VoiceStatus = "off" | "connecting" | "listening" | "thinking" | "speaking" | "unavailable";

export interface VoiceCallbacks {
  onStatus: (s: VoiceStatus) => void;
  onCaption: (c: { role: string; text: string; final: boolean }) => void;
  onLevel?: (peak: number) => void;
}

/**
 * One voice conversation for one kiosk session (/ws/voice). Audio never touches storage: mic frames go
 * straight to the backend relay and assistant audio straight to the speakers. The browser's echo
 * cancellation keeps the assistant's own voice out of the microphone so barge-in works.
 */
export class VoiceSession {
  private ws: WebSocket | null = null;
  private mic: MediaStream | null = null;
  private captureCtx: AudioContext | null = null;
  private playbackCtx: AudioContext | null = null;
  private player: AudioWorkletNode | null = null;
  private closed = false;
  muted = false;

  constructor(
    private token: string,
    private cb: VoiceCallbacks,
  ) {}

  start(): void {
    this.cb.onStatus("connecting");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/voice`);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "auth", token: this.token }));
    ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        this.player?.port.postMessage(ev.data, [ev.data]);
        return;
      }
      const msg = JSON.parse(String(ev.data));
      switch (msg.type) {
        case "voice.ready":
          void this.startAudio(msg.input_rate, msg.output_rate);
          break;
        case "audio.interrupt":
          this.player?.port.postMessage("flush");
          break;
        case "caption":
          this.cb.onCaption(msg);
          break;
        case "voice.status":
          this.cb.onStatus(msg.status);
          break;
        case "voice.unavailable":
          this.cb.onStatus("unavailable");
          break;
      }
    };
    ws.onclose = () => {
      if (!this.closed) this.cb.onStatus("unavailable");
      this.teardownAudio();
    };
  }

  private async startAudio(inputRate: number, outputRate: number): Promise<void> {
    try {
      this.playbackCtx = new AudioContext({ sampleRate: outputRate });
      await this.playbackCtx.audioWorklet.addModule(playbackUrl);
      this.player = new AudioWorkletNode(this.playbackCtx, "playback-processor");
      this.player.connect(this.playbackCtx.destination);
      this.player.port.onmessage = (e) => {
        if (e.data?.playing === false) this.cb.onStatus("listening");
      };

      this.mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      this.captureCtx = new AudioContext({ sampleRate: inputRate });
      await this.captureCtx.audioWorklet.addModule(captureUrl);
      const source = this.captureCtx.createMediaStreamSource(this.mic);
      const capture = new AudioWorkletNode(this.captureCtx, "capture-processor");
      capture.port.onmessage = (e) => {
        this.cb.onLevel?.(e.data.peak);
        if (!this.muted && this.ws?.readyState === WebSocket.OPEN) this.ws.send(e.data.pcm);
      };
      source.connect(capture);
      this.cb.onStatus("listening");
    } catch {
      // No microphone or permission denied: voice off, touch continues.
      this.cb.onStatus("unavailable");
      this.stop();
    }
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "mute", muted }));
  }

  private teardownAudio(): void {
    this.mic?.getTracks().forEach((t) => t.stop());
    void this.captureCtx?.close().catch(() => undefined);
    void this.playbackCtx?.close().catch(() => undefined);
    this.mic = null;
    this.captureCtx = this.playbackCtx = null;
    this.player = null;
  }

  stop(): void {
    this.closed = true;
    this.ws?.close();
    this.teardownAudio();
    this.cb.onStatus("off");
  }
}
