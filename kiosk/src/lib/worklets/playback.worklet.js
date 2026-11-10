// PCM16 chunks -> speakers through a ring buffer. "flush" drops everything instantly (barge-in).
class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ring = new Float32Array(sampleRate * 30);
    this.read = 0;
    this.write = 0;
    this.playing = false;
    this.port.onmessage = (e) => {
      if (e.data === "flush") {
        this.read = this.write = 0;
        return;
      }
      const pcm = new Int16Array(e.data);
      for (let i = 0; i < pcm.length; i++) {
        this.ring[this.write] = pcm[i] / 0x8000;
        this.write = (this.write + 1) % this.ring.length;
        if (this.write === this.read) this.read = (this.read + 1) % this.ring.length; // overflow: drop oldest
      }
    };
  }
  process(_inputs, outputs) {
    const out = outputs[0][0];
    let n = 0;
    for (let i = 0; i < out.length; i++) {
      if (this.read !== this.write) {
        out[i] = this.ring[this.read];
        this.read = (this.read + 1) % this.ring.length;
        n++;
      } else out[i] = 0;
    }
    const playing = n > 0;
    if (playing !== this.playing) {
      this.playing = playing;
      this.port.postMessage({ playing });
    }
    return true;
  }
}
registerProcessor("playback-processor", PlaybackProcessor);
