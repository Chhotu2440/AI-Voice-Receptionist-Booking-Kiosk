// Copies the MediaPipe WASM runtime into public/ so the kiosk never loads code from a CDN at runtime.
// The face model (public/models/blaze_face_short_range.tflite, Apache-2.0) is committed and verified here.
import { createHash } from "node:crypto";
import { cpSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "@mediapipe", "tasks-vision", "wasm");
const dest = join(root, "public", "mediapipe", "wasm");
mkdirSync(dest, { recursive: true });
cpSync(src, dest, { recursive: true });

const MODEL_SHA256 = "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f";
const model = readFileSync(join(root, "public", "models", "blaze_face_short_range.tflite"));
const digest = createHash("sha256").update(model).digest("hex");
if (digest !== MODEL_SHA256) {
  console.error(`face model checksum mismatch: ${digest}`);
  process.exit(1);
}
console.log("mediapipe runtime copied; face model verified");
