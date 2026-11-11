import { useEffect, useRef } from "react";

import { audioLevel, useKiosk } from "../store";

/**
 * The receptionist robot. Its mouth is driven by the real output audio level (so lips move only while
 * it actually speaks), its eyes blink and glance, its ears light up green while the customer is talking,
 * and it "thinks" (eyes up, orbiting dots) while a tool call runs. Animation runs in requestAnimationFrame
 * outside React, so 60 fps costs no re-renders.
 */
export function Robot({ size = 300 }: { size?: number }) {
  const status = useKiosk((s) => s.voice.status);
  const userSpeaking = useKiosk((s) => s.voice.userSpeaking);
  const bars = useRef<(SVGRectElement | null)[]>([]);
  const eyes = useRef<(SVGEllipseElement | null)[]>([]);
  const glow = useRef<SVGCircleElement | null>(null);

  useEffect(() => {
    let raf = 0;
    let smooth = 0;
    let blinkAt = performance.now() + 2500;
    let glanceX = 0;
    let glanceTarget = 0;
    const tick = (now: number) => {
      // Mouth: equaliser bars from the speech envelope with a little per-bar variation.
      const target = Math.min(1, audioLevel.output * 6);
      smooth += (target - smooth) * (target > smooth ? 0.55 : 0.18);
      bars.current.forEach((bar, i) => {
        if (!bar) return;
        const wobble = 0.55 + 0.45 * Math.sin(now / (70 + i * 23) + i * 1.7);
        const h = 6 + 46 * smooth * wobble * (i === 2 ? 1 : i % 2 ? 0.85 : 0.65);
        bar.setAttribute("height", String(h));
        bar.setAttribute("y", String(232 - h / 2));
      });
      // Eyes: blink every few seconds, glance occasionally.
      let open = 1;
      if (now > blinkAt) {
        const t = (now - blinkAt) / 140;
        open = t < 1 ? 1 - t : t < 2 ? t - 1 : 1;
        if (t >= 2) blinkAt = now + 2500 + Math.random() * 3500;
      }
      if (Math.random() < 0.004) glanceTarget = (Math.random() - 0.5) * 14;
      glanceX += (glanceTarget - glanceX) * 0.05;
      eyes.current.forEach((eye, i) => {
        if (!eye) return;
        eye.setAttribute("ry", String(Math.max(2, 22 * open)));
        eye.setAttribute("cx", String((i === 0 ? 120 : 200) + glanceX));
      });
      if (glow.current) glow.current.setAttribute("opacity", String(0.25 + smooth * 0.6));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const thinking = status === "thinking";
  const accent = status === "speaking" ? "#FF2BD6" : userSpeaking ? "#B6FF3B" : "#22E4FF";
  return (
    <div className="relative mx-auto select-none" style={{ width: size, height: size }} data-voice={status} aria-hidden>
      <svg viewBox="0 0 320 320" width={size} height={size}>
        <defs>
          <radialGradient id="face" cx="50%" cy="40%" r="65%">
            <stop offset="0%" stopColor="#1B2036" />
            <stop offset="100%" stopColor="#07080F" />
          </radialGradient>
          <filter id="neon" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <circle ref={glow} cx="160" cy="170" r="150" fill={accent} opacity="0.25" style={{ filter: "blur(28px)" }} />
        {/* antenna */}
        <line x1="160" y1="58" x2="160" y2="28" stroke="#A3A9C2" strokeWidth="5" strokeLinecap="round" />
        <circle cx="160" cy="22" r="10" fill={accent} filter="url(#neon)">
          <animate attributeName="opacity" values="1;0.35;1" dur={thinking ? "0.6s" : "2.2s"} repeatCount="indefinite" />
        </circle>
        {/* ears: light up while the customer is talking */}
        <rect x="18" y="128" width="26" height="74" rx="12" fill={userSpeaking ? "#B6FF3B" : "#232842"} filter={userSpeaking ? "url(#neon)" : undefined} />
        <rect x="276" y="128" width="26" height="74" rx="12" fill={userSpeaking ? "#B6FF3B" : "#232842"} filter={userSpeaking ? "url(#neon)" : undefined} />
        {/* head */}
        <rect x="40" y="58" width="240" height="230" rx="64" fill="url(#face)" stroke={accent} strokeWidth="5" filter="url(#neon)" />
        {/* visor */}
        <rect x="70" y="100" width="180" height="96" rx="44" fill="#0B0D18" stroke="#232842" strokeWidth="3" />
        {[0, 1].map((i) => (
          <ellipse
            key={i}
            ref={(el) => {
              eyes.current[i] = el;
            }}
            cx={i === 0 ? 120 : 200}
            cy={thinking ? 136 : 148}
            rx="18"
            ry="22"
            fill={accent}
            filter="url(#neon)"
          />
        ))}
        {/* mouth: audio-driven equaliser */}
        {[0, 1, 2, 3, 4].map((i) => (
          <rect
            key={i}
            ref={(el) => {
              bars.current[i] = el;
            }}
            x={118 + i * 18}
            y={229}
            width="12"
            height="6"
            rx="6"
            fill={accent}
            filter="url(#neon)"
          />
        ))}
        {/* thinking: orbiting dots */}
        {thinking ? (
          <g>
            {[0, 1, 2].map((i) => (
              <circle key={i} r="6" fill="#22E4FF">
                <animateMotion dur="1.4s" begin={`${i * 0.2}s`} repeatCount="indefinite" path="M160,40 a120,120 0 1,1 -0.1,0" />
              </circle>
            ))}
          </g>
        ) : null}
      </svg>
      <div className="absolute inset-x-0 -bottom-2 text-center text-xl font-semibold tracking-wide" style={{ color: accent }}>
        <StatusLabel />
      </div>
    </div>
  );
}

function StatusLabel() {
  const status = useKiosk((s) => s.voice.status);
  const userSpeaking = useKiosk((s) => s.voice.userSpeaking);
  const muted = useKiosk((s) => s.voice.muted);
  const lang = useKiosk((s) => s.state?.language ?? "en");
  const hi = lang === "hi";
  if (status === "off" || status === "unavailable") return null;
  if (muted) return <span>{hi ? "माइक बंद" : "Mic off"}</span>;
  if (userSpeaking) return <span>{hi ? "सुन रही हूँ…" : "Listening…"}</span>;
  if (status === "thinking") return <span>{hi ? "देख रही हूँ…" : "Checking…"}</span>;
  if (status === "speaking") return <span>{hi ? "बोल रही हूँ" : "Speaking"}</span>;
  if (status === "connecting") return <span>{hi ? "जुड़ रही हूँ…" : "Connecting…"}</span>;
  return <span>{hi ? "आप बोल सकते हैं" : "You can talk to me"}</span>;
}
