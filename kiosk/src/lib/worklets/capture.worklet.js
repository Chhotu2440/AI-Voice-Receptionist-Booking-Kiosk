// Microphone -> PCM16 frames. The AudioContext runs at the provider's input rate, so the browser does the
// resampling; we only convert Float32 to Int16 and batch ~40 ms per message.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = Math.round(sampleRate * 0.04);
    this.buf = new Int16Array(this.frame);
    this.len = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    let peak = 0;
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      peak = Math.max(peak, Math.abs(s));
      this.buf[this.len++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.len === this.frame) {
        this.port.postMessage({ pcm: this.buf.buffer, peak }, [this.buf.buffer]);
        this.buf = new Int16Array(this.frame);
        this.len = 0;
        peak = 0;
      }
    }
    return true;
  }
}
registerProcessor("capture-processor", CaptureProcessor);
