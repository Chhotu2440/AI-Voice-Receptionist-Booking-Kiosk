/**
 * Microphone gate (pure, unit-tested). Decides which mic frames reach the voice model.
 *
 * Two problems it solves at a noisy reception with ordinary speakers:
 * 1. Echo: while the assistant is talking, its own voice leaks into the mic and the model may "hear" it
 *    as the customer. During playback only clearly louder speech opens the gate (barge-in).
 * 2. Noise: background hum, music and distant chatter. The gate tracks the noise floor and opens only
 *    for frames well above it, with a short pre-roll so the first syllable isn't lost, and a hang-over
 *    so pauses inside a sentence don't cut the customer off.
 * Closed-gate frames are replaced by digital silence (not dropped), so the model's own voice-activity
 * detection still sees the end of speech.
 */

export interface GateConfig {
  minSpeechPeak: number; // absolute floor for "speech" when the assistant is silent
  floorMultiplier: number; // speech must be this many times above the learned noise floor
  bargeInPeak: number; // while the assistant talks, interruptions must be at least this loud
  bargeInFrames: number; // ...for this many consecutive frames
  preRollFrames: number;
  hangoverFrames: number;
}

export const DEFAULT_GATE: GateConfig = {
  minSpeechPeak: 0.04,
  floorMultiplier: 3.5,
  bargeInPeak: 0.3,
  bargeInFrames: 3,
  preRollFrames: 8, // 8 x 40 ms = 320 ms
  hangoverFrames: 20, // 800 ms
};

export interface GateOutput {
  send: ArrayBuffer[]; // frames to send now (pre-roll + current), in order
  open: boolean;
}

export class MicGate {
  private floor = 0.01;
  private open = false;
  private loudRun = 0;
  private hang = 0;
  private preRoll: ArrayBuffer[] = [];

  constructor(private cfg: GateConfig = DEFAULT_GATE) {}

  get noiseFloor(): number {
    return this.floor;
  }

  /** `peak` is the frame's max |sample| (0..1); `assistantSpeaking` = playback active. */
  push(frame: ArrayBuffer, peak: number, assistantSpeaking: boolean): GateOutput {
    const threshold = assistantSpeaking
      ? Math.max(this.cfg.bargeInPeak, this.floor * this.cfg.floorMultiplier * 2)
      : Math.max(this.cfg.minSpeechPeak, this.floor * this.cfg.floorMultiplier);
    const loud = peak >= threshold;
    this.loudRun = loud ? this.loudRun + 1 : 0;

    if (!loud && !this.open && !assistantSpeaking) {
      // Learn the room's noise floor only from quiet, non-playback frames (slow attack, faster release).
      const rate = peak > this.floor ? 0.02 : 0.1;
      this.floor = Math.min(0.2, this.floor + (peak - this.floor) * rate);
    }

    const needed = assistantSpeaking ? this.cfg.bargeInFrames : 1;
    if (!this.open && this.loudRun >= needed) {
      this.open = true;
      this.hang = this.cfg.hangoverFrames;
      const out = [...this.preRoll, frame];
      this.preRoll = [];
      return { send: out, open: true };
    }
    if (this.open) {
      if (loud) this.hang = this.cfg.hangoverFrames;
      else if (--this.hang <= 0) this.open = false;
      return { send: [this.open ? frame : silenceLike(frame)], open: this.open };
    }
    this.preRoll.push(frame);
    if (this.preRoll.length > this.cfg.preRollFrames) this.preRoll.shift();
    return { send: [silenceLike(frame)], open: false };
  }
}

function silenceLike(frame: ArrayBuffer): ArrayBuffer {
  return new ArrayBuffer(frame.byteLength);
}
