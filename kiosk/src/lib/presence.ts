/**
 * Presence logic (CAM-01). Pure and deterministic: fed with face *detections* (boxes + 6 keypoints from
 * MediaPipe BlazeFace), never with images. No identity, no embeddings, no age/gender/emotion (doc 16 §3).
 *
 * "Arrived" = a face that is big enough (close to the kiosk) and roughly frontal (looking at the screen)
 * for `dwellMs` continuously, so people walking past don't trigger a greeting.
 * "Left"    = no such face (with a relaxed size threshold) for `leaveMs`.
 */

export interface Point {
  x: number; // 0..1 of frame width
  y: number;
}

export interface Face {
  x: number;
  y: number;
  w: number; // 0..1 of frame width
  h: number; // 0..1 of frame height
  score: number;
  keypoints: Point[]; // BlazeFace order: right eye, left eye, nose tip, mouth, right ear, left ear
}

export interface PresenceConfig {
  minFaceArea: number; // fraction of frame (≈ distance threshold)
  maxYaw: number; // |nose offset from eye midpoint| / eye distance
  minScore: number;
  dwellMs: number;
  leaveMs: number;
  gapToleranceMs: number; // brief detection dropouts while dwelling
}

export const DEFAULT_PRESENCE: PresenceConfig = {
  minFaceArea: 0.02,
  maxYaw: 0.35,
  minScore: 0.6,
  dwellMs: 1500,
  leaveMs: 15_000,
  gapToleranceMs: 400,
};

export type PresenceEvent = "arrived" | "left";

export function isFrontal(face: Face, maxYaw: number): boolean {
  const [rEye, lEye, nose] = face.keypoints;
  if (!rEye || !lEye || !nose) return false;
  const eyeDist = Math.hypot(lEye.x - rEye.x, lEye.y - rEye.y);
  if (eyeDist <= 0) return false;
  const midX = (lEye.x + rEye.x) / 2;
  return Math.abs(nose.x - midX) / eyeDist <= maxYaw;
}

export function engaged(face: Face, cfg: PresenceConfig, areaFactor = 1): boolean {
  return face.score >= cfg.minScore && face.w * face.h >= cfg.minFaceArea * areaFactor && isFrontal(face, cfg.maxYaw);
}

export class PresenceTracker {
  present = false;
  private dwellStart: number | null = null;
  private lastEngaged: number | null = null;
  private lastSeen: number | null = null;

  constructor(private cfg: PresenceConfig = DEFAULT_PRESENCE) {}

  setConfig(cfg: PresenceConfig): void {
    this.cfg = cfg;
  }

  reset(): void {
    this.present = false;
    this.dwellStart = this.lastEngaged = this.lastSeen = null;
  }

  update(faces: Face[], now: number): PresenceEvent | null {
    const engagedNow = faces.some((f) => engaged(f, this.cfg));
    // Once present, keep the person "seen" even if they glance away or step back a little.
    const seenNow = faces.some((f) => f.score >= this.cfg.minScore && f.w * f.h >= this.cfg.minFaceArea * 0.5);

    if (!this.present) {
      if (engagedNow) {
        if (this.dwellStart === null || (this.lastEngaged !== null && now - this.lastEngaged > this.cfg.gapToleranceMs)) {
          this.dwellStart = now;
        }
        this.lastEngaged = now;
        if (now - this.dwellStart >= this.cfg.dwellMs) {
          this.present = true;
          this.lastSeen = now;
          this.dwellStart = null;
          return "arrived";
        }
      } else if (this.lastEngaged !== null && now - this.lastEngaged > this.cfg.gapToleranceMs) {
        this.dwellStart = null;
      }
      return null;
    }

    if (seenNow) this.lastSeen = now;
    if (this.lastSeen !== null && now - this.lastSeen >= this.cfg.leaveMs) {
      this.reset();
      return "left";
    }
    return null;
  }
}
