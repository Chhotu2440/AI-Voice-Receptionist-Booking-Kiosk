import { describe, expect, it } from "vitest";

import { DEFAULT_PRESENCE, PresenceTracker, isFrontal, type Face } from "./presence";

// Explicit thresholds so these tests don't change when the venue defaults are tuned.
const CFG = { ...DEFAULT_PRESENCE, minFaceArea: 0.02, maxYaw: 0.35, minScore: 0.6, dwellMs: 1500, leaveMs: 15_000 };

/** A face centred at (cx, cy) with relative size `size`; `yaw` shifts the nose sideways. */
function face(size = 0.25, yaw = 0, score = 0.9): Face {
  const cx = 0.5;
  const cy = 0.45;
  const eye = size * 0.35;
  return {
    x: cx - size / 2,
    y: cy - size / 2,
    w: size,
    h: size,
    score,
    keypoints: [
      { x: cx - eye / 2, y: cy - 0.03 },
      { x: cx + eye / 2, y: cy - 0.03 },
      { x: cx + yaw * eye, y: cy },
      { x: cx, y: cy + 0.05 },
      { x: cx - size / 2, y: cy },
      { x: cx + size / 2, y: cy },
    ],
  };
}

function run(tracker: PresenceTracker, frames: [number, Face[]][]) {
  return frames.map(([t, f]) => tracker.update(f, t)).filter(Boolean);
}

const every200 = (from: number, to: number, faces: Face[]) => {
  const out: [number, Face[]][] = [];
  for (let t = from; t <= to; t += 200) out.push([t, faces]);
  return out;
};

describe("presence", () => {
  it("detects frontal vs turned faces", () => {
    expect(isFrontal(face(0.25, 0), 0.35)).toBe(true);
    expect(isFrontal(face(0.25, 0.6), 0.35)).toBe(false);
  });

  it("greets only after the dwell time", () => {
    const tr = new PresenceTracker(CFG);
    expect(run(tr, every200(0, 1400, [face()]))).toEqual([]);
    expect(tr.update([face()], 1600)).toBe("arrived");
    expect(tr.present).toBe(true);
  });

  it("ignores people walking past (short dwell), far away, or looking sideways", () => {
    const tr = new PresenceTracker(CFG);
    expect(run(tr, every200(0, 800, [face()]))).toEqual([]);
    expect(run(tr, every200(1000, 4000, []))).toEqual([]);
    expect(run(tr, every200(4200, 9000, [face(0.08)]))).toEqual([]); // area 0.0064 < 0.02
    expect(run(tr, every200(9200, 14000, [face(0.25, 0.8)]))).toEqual([]);
    expect(run(tr, every200(14200, 20000, [face(0.25, 0, 0.3)]))).toEqual([]); // low confidence
  });

  it("tolerates brief detection dropouts while dwelling", () => {
    const tr = new PresenceTracker(CFG);
    const frames: [number, Face[]][] = [
      [0, [face()]],
      [200, [face()]],
      [400, []], // 1 dropped frame
      [600, [face()]],
      [800, [face()]],
      [1000, [face()]],
      [1200, [face()]],
      [1400, [face()]],
      [1600, [face()]],
    ];
    expect(run(tr, frames)).toEqual(["arrived"]);
  });

  it("restarts the dwell after a longer gap", () => {
    const tr = new PresenceTracker(CFG);
    run(tr, every200(0, 1000, [face()]));
    run(tr, every200(1200, 2400, []));
    expect(run(tr, every200(2600, 3800, [face()]))).toEqual([]);
    expect(tr.update([face()], 4200)).toBe("arrived");
  });

  it("reports leaving only after leaveMs without anyone, and keeps glancing customers", () => {
    const tr = new PresenceTracker(CFG);
    run(tr, every200(0, 1600, [face()]));
    expect(tr.present).toBe(true);
    // Looking down at the screen (turned) or stepping back a bit still counts as there.
    expect(run(tr, every200(1800, 20000, [face(0.15, 0.8)]))).toEqual([]);
    expect(run(tr, every200(20200, 34800, []))).toEqual([]); // last seen at 20000
    expect(tr.update([], 35000)).toBe("left");
    expect(tr.present).toBe(false);
  });

  it("uses configurable thresholds", () => {
    const tr = new PresenceTracker({ ...DEFAULT_PRESENCE, dwellMs: 600, minFaceArea: 0.005 });
    expect(run(tr, every200(0, 600, [face(0.08)]))).toEqual(["arrived"]);
  });
});
