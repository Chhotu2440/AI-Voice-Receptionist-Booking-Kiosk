import { MicGate } from "./voiceGate";
import captureUrl from "./worklets/capture.worklet.js?url";
import playbackUrl from "./worklets/playback.worklet.js?url";

export type VoiceStatus = "off" | "connecting" | "listening" | "thinking" | "speaking" | "unavailable";

export interface VoiceCallbacks {
  onStatus: (s: VoiceStatus) => void;
  onCaption: (c: { role: string; text: string; final: boolean }) => void;
  /** Assistant output level 0..1 (~30/s) - drives the robot's mouth. */
  onOutputLevel?: (level: number) => void;
  /** The customer is speaking (mic gate open) - counts as activity, drives the "listening" ears. */
  onUserSpeaking?: (speaking: boolean) => void;
}

/**
 * One voice conversation for one kiosk session (/ws/voice). Audio never touches storage: mic frames go
 * to the backend relay and assistant audio to the speakers.
 *
 * Echo handling, belt and braces:
 * - assistant audio is played through an <audio> element fed by a MediaStream, which puts it on the
 *   browser's echo-cancellation reference path (raw AudioContext output may not be);
 * - the MicGate only lets clearly louder speech through while the assistant is talking, and keeps steady
 *   background noise out the rest of the time.
 */
export class VoiceSession {
  private ws: WebSocket | null = null;
  private mic: MediaStream | null = null;
  private captureCtx: AudioContext | null = null;
  private playbackCtx: AudioContext | null = null;
  private player: AudioWorkletNode | null = null;
  private audioEl: HTMLAudioElement | null = null;
  private gain: GainNode | null = null;
  private volume = 0.7; // 0..1, from the kiosk's admin config
  private gate = new MicGate();
  private playing = false;
  private userSpeaking = false;
  private closed = false;
  muted = false;

  constructor(
    private token: string,
    private cb: VoiceCallbacks,
  ) {}

  /** Assistant voice volume, 0-100 (admin: Kiosks -> Settings -> Volume). Applies immediately. */
  setVolume(percent: number): void {
    this.volume = Math.min(1, Math.max(0, (Number.isFinite(percent) ? percent : 70) / 100));
    if (this.gain) this.gain.gain.value = this.volume;
  }

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
          if (msg.status !== "listening" || !this.playing) this.cb.onStatus(msg.status);
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
      const dest = this.playbackCtx.createMediaStreamDestination();
      this.gain = this.playbackCtx.createGain();
      this.gain.gain.value = this.volume;
      this.player.connect(this.gain);
      this.gain.connect(dest);
      this.audioEl = new Audio();
      this.audioEl.srcObject = dest.stream;
      await this.audioEl.play().catch(() => {
        // Autoplay blocked (shouldn't happen after a tap / in kiosk mode): fall back to direct output.
        this.gain?.connect(this.playbackCtx!.destination);
      });
      this.player.port.onmessage = (e) => {
        if (typeof e.data?.playing === "boolean") {
          this.playing = e.data.playing;
          this.cb.onStatus(this.playing ? "speaking" : "listening");
        } else if (typeof e.data?.level === "number") {
          this.cb.onOutputLevel?.(this.playing ? e.data.level : 0);
        }
      };

      this.mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      this.captureCtx = new AudioContext({ sampleRate: inputRate });
      await this.captureCtx.audioWorklet.addModule(captureUrl);
      const source = this.captureCtx.createMediaStreamSource(this.mic);
      const capture = new AudioWorkletNode(this.captureCtx, "capture-processor");
      capture.port.onmessage = (e) => this.onMicFrame(e.data.pcm as ArrayBuffer, e.data.peak as number);
      source.connect(capture);
      this.cb.onStatus("listening");
    } catch {
      // No microphone or permission denied: voice off, touch continues.
      this.cb.onStatus("unavailable");
      this.stop();
    }
  }

  private onMicFrame(pcm: ArrayBuffer, peak: number): void {
    if (this.muted || this.ws?.readyState !== WebSocket.OPEN) return;
    const { send, open } = this.gate.push(pcm, peak, this.playing);
    if (open !== this.userSpeaking) {
      this.userSpeaking = open;
      this.cb.onUserSpeaking?.(open);
      if (open && this.playing) this.player?.port.postMessage("flush"); // barge-in: stop talking at once
    }
    for (const frame of send) this.ws.send(frame);
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "mute", muted }));
  }

  private teardownAudio(): void {
    this.mic?.getTracks().forEach((t) => t.stop());
    void this.captureCtx?.close().catch(() => undefined);
    void this.playbackCtx?.close().catch(() => undefined);
    if (this.audioEl) this.audioEl.srcObject = null;
    this.mic = null;
    this.captureCtx = this.playbackCtx = null;
    this.player = null;
    this.audioEl = null;
  }

  stop(): void {
    this.closed = true;
    this.ws?.close();
    this.teardownAudio();
    this.cb.onStatus("off");
  }
}
