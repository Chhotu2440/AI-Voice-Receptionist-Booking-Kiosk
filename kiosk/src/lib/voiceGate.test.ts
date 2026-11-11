import { describe, expect, it } from "vitest";

import { MicGate } from "./voiceGate";

const frame = (tag: number) => {
  const b = new ArrayBuffer(4);
  new Int16Array(b)[0] = tag;
  return b;
};
const isSilence = (b: ArrayBuffer) => new Int16Array(b).every((v) => v === 0);

describe("MicGate", () => {
  it("keeps steady background noise out and learns the noise floor", () => {
    const g = new MicGate();
    for (let i = 0; i < 200; i++) {
      const out = g.push(frame(i + 1), 0.03 + (i % 3) * 0.002, false);
      expect(out.open).toBe(false);
      expect(out.send.every(isSilence)).toBe(true);
    }
    expect(g.noiseFloor).toBeGreaterThan(0.02);
  });

  it("opens on speech with pre-roll and closes after the hang-over", () => {
    const g = new MicGate();
    for (let i = 0; i < 20; i++) g.push(frame(100 + i), 0.01, false);
    const opened = g.push(frame(999), 0.3, false);
    expect(opened.open).toBe(true);
    expect(opened.send.length).toBe(9); // 8 pre-roll frames + current
    expect(new Int16Array(opened.send[8]!)[0]).toBe(999);
    // A short pause inside the sentence keeps the gate open...
    for (let i = 0; i < 10; i++) expect(g.push(frame(1), 0.01, false).open).toBe(true);
    // ...a long silence closes it.
    let open = true;
    for (let i = 0; i < 30; i++) open = g.push(frame(1), 0.01, false).open;
    expect(open).toBe(false);
  });

  it("ignores the assistant's own echo during playback but allows a loud interruption", () => {
    const g = new MicGate();
    for (let i = 0; i < 20; i++) g.push(frame(1), 0.01, false);
    for (let i = 0; i < 50; i++) expect(g.push(frame(2), 0.15, true).open).toBe(false); // echo level
    expect(g.push(frame(3), 0.5, true).open).toBe(false);
    expect(g.push(frame(3), 0.5, true).open).toBe(false);
    expect(g.push(frame(3), 0.5, true).open).toBe(true); // 3 loud frames in a row = barge-in
  });
});
