import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";

import { PresenceTracker, type Face, type PresenceConfig, type PresenceEvent } from "./presence";

/**
 * On-device presence detection (ADR-009). Frames go from the webcam straight into MediaPipe in this
 * browser tab; only the boolean outcome leaves this module. Frames are never drawn, stored or sent.
 */
export interface PresenceHandle {
  stop: () => void;
  setConfig: (cfg: PresenceConfig) => void;
}

export interface PresenceCallbacks {
  onEvent: (e: PresenceEvent) => void;
  onHealth: (cameraOk: boolean, detail?: string) => void;
  onFaces?: (count: number, present: boolean) => void;
}

const FRAME_INTERVAL_MS = 200; // ~5 fps is plenty for presence and keeps the CPU cool

async function createDetector(): Promise<FaceDetector> {
  const fileset = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
  const options = (delegate: "GPU" | "CPU") => ({
    baseOptions: { modelAssetPath: "/models/blaze_face_short_range.tflite", delegate },
    runningMode: "VIDEO" as const,
    minDetectionConfidence: 0.5,
  });
  try {
    return await FaceDetector.createFromOptions(fileset, options("GPU"));
  } catch {
    return await FaceDetector.createFromOptions(fileset, options("CPU"));
  }
}

export async function startPresence(cfg: PresenceConfig, cb: PresenceCallbacks): Promise<PresenceHandle> {
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
      audio: false,
    });
  } catch (e) {
    cb.onHealth(false, e instanceof Error ? e.name : "camera unavailable");
    return { stop: () => undefined, setConfig: () => undefined };
  }

  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.srcObject = stream;
  await video.play().catch(() => undefined);

  let detector: FaceDetector;
  try {
    detector = await createDetector();
  } catch (e) {
    stream.getTracks().forEach((t) => t.stop());
    cb.onHealth(false, e instanceof Error ? e.message : "detector failed");
    return { stop: () => undefined, setConfig: () => undefined };
  }
  cb.onHealth(true);

  const tracker = new PresenceTracker(cfg);
  let lastTs = 0;
  const timer = window.setInterval(() => {
    if (video.readyState < 2 || !video.videoWidth) return;
    const now = performance.now();
    if (now <= lastTs) return;
    lastTs = now;
    let faces: Face[] = [];
    try {
      const result = detector.detectForVideo(video, now);
      faces = result.detections.map((d) => {
        const box = d.boundingBox ?? { originX: 0, originY: 0, width: 0, height: 0 };
        return {
          x: box.originX / video.videoWidth,
          y: box.originY / video.videoHeight,
          w: box.width / video.videoWidth,
          h: box.height / video.videoHeight,
          score: d.categories[0]?.score ?? 0,
          keypoints: d.keypoints.map((k) => ({ x: k.x, y: k.y })),
        };
      });
    } catch {
      return;
    }
    const event = tracker.update(faces, Date.now());
    cb.onFaces?.(faces.length, tracker.present);
    if (event) cb.onEvent(event);
  }, FRAME_INTERVAL_MS);

  const track = stream.getVideoTracks()[0];
  track?.addEventListener("ended", () => cb.onHealth(false, "camera disconnected"));

  return {
    stop: () => {
      window.clearInterval(timer);
      detector.close();
      stream.getTracks().forEach((t) => t.stop());
      video.srcObject = null;
    },
    setConfig: (c) => tracker.setConfig(c),
  };
}
