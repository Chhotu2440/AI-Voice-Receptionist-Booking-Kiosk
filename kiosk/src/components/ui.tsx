import { useEffect, useState, type ReactNode } from "react";

import { useKiosk, useT } from "../store";
import type { KioskStateName } from "../types";

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  className = "",
  testId,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  disabled?: boolean;
  className?: string;
  testId?: string;
}) {
  const pending = useKiosk((s) => s.pending);
  const styles = {
    primary: "bg-laser text-arena-950 shadow-laser active:scale-[0.98]",
    secondary: "bg-arena-700 text-ink border border-arena-600 active:bg-arena-600",
    ghost: "bg-transparent text-ink-muted active:text-ink",
    danger: "bg-plasma text-arena-950 shadow-plasma",
  }[variant];
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={disabled || pending !== null}
      className={`min-h-[72px] rounded-2xl px-8 text-[26px] font-semibold transition duration-75 disabled:opacity-40 ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Tile({
  children,
  onClick,
  selected,
  disabled,
  testId,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  selected?: boolean;
  disabled?: boolean;
  testId?: string;
  className?: string;
}) {
  const pending = useKiosk((s) => s.pending);
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={disabled || pending !== null}
      className={`rounded-2xl border p-5 text-left transition duration-75 active:scale-[0.98] disabled:opacity-35 ${
        selected ? "border-laser bg-arena-700 shadow-laser" : "border-arena-600 bg-arena-800"
      } ${className}`}
    >
      {children}
    </button>
  );
}

export function Assistant() {
  const status = useKiosk((s) => s.voice.status);
  const speaking = status === "speaking";
  const listening = status === "listening";
  return (
    <div className="relative mx-auto h-56 w-56" aria-hidden data-voice={status}>
      <div className={`absolute inset-0 rounded-full blur-2xl ${speaking ? "bg-plasma/25" : "bg-laser/10"}`} />
      <div
        className={`absolute inset-6 rounded-full border-4 bg-gradient-to-br from-arena-700 to-arena-950 ${
          speaking ? "animate-pulse border-plasma" : listening ? "border-signal" : "animate-breathe border-laser/80"
        }`}
      />
      <div className={`absolute inset-[38%] rounded-full shadow-laser ${speaking ? "bg-plasma" : "bg-laser"}`} />
      <div className="absolute left-1/2 top-[18%] h-[64%] w-1 -translate-x-1/2 rounded bg-plasma/60" />
    </div>
  );
}

const STEP_OF: Partial<Record<KioskStateName, number>> = {
  CUSTOMER_NAME: 0,
  CUSTOMER_PHONE: 0,
  GUEST_COUNT: 1,
  OCCASION: 1,
  CUSTOM_EVENT_DETAILS: 1,
  PACKAGE_DISCOVERY: 2,
  DATE_SELECTION: 3,
  SLOT_SELECTION: 3,
  BOOKING_SUMMARY: 4,
  BOOKING_CONFIRMED: 5,
  SESSION_COMPLETE: 5,
};

export function ProgressRail() {
  const { t } = useT();
  const state = useKiosk((s) => s.state?.state);
  const current = state ? STEP_OF[state] : undefined;
  if (current === undefined) return null;
  return (
    <ol className="flex gap-3" aria-label="progress">
      {t.steps.map((label, i) => (
        <li key={label} className="flex items-center gap-3">
          <span
            className={`flex h-10 items-center rounded-full px-4 text-lg font-semibold ${
              i < current ? "bg-laser/20 text-laser" : i === current ? "bg-laser text-arena-950" : "bg-arena-700 text-ink-muted"
            }`}
          >
            {label}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Two-column kiosk frame: assistant + prompt on the left, interaction on the right, bar at the bottom. */
export function Screen({ prompt, sub, children }: { prompt: string; sub?: string; children: ReactNode }) {
  const { t, lang } = useT();
  const send = useKiosk((s) => s.send);
  const allowed = useKiosk((s) => s.allowed);
  const toast = useKiosk((s) => s.toast);
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between px-10 pt-8">
        <div className="font-display text-2xl tracking-widest text-laser">PLAY LASER TAG</div>
        <ProgressRail />
      </header>
      <main className="flex min-h-0 flex-1 gap-10 px-10 py-6">
        <section className="flex w-[32%] flex-col justify-center gap-8 animate-rise">
          <Assistant />
          <h1 className="font-display text-[40px] leading-tight" data-testid="prompt">
            {prompt}
          </h1>
          {sub ? <p className="text-2xl text-ink-muted">{sub}</p> : null}
          <VoiceCaption />
        </section>
        <section className="flex min-h-0 flex-1 flex-col justify-center animate-rise">{children}</section>
      </main>
      {toast ? (
        <div role="alert" data-testid="toast" className="mx-10 mb-3 rounded-xl border border-alert/60 bg-alert/10 px-6 py-4 text-2xl text-alert">
          {toast.message}
        </div>
      ) : null}
      <footer className="flex items-center justify-between border-t border-arena-700 px-10 py-5">
        <div className="flex gap-4">
          {allowed.includes("back") ? (
            <Button variant="secondary" onClick={() => send("back")} testId="back">
              ← {t.back}
            </Button>
          ) : null}
          {allowed.includes("cancel") ? (
            <Button variant="ghost" onClick={() => send("cancel")} testId="start-over">
              {t.startOver}
            </Button>
          ) : null}
        </div>
        <div className="flex gap-4">
          <MicToggle />
          <Button
            variant="secondary"
            onClick={() => send("set_language", { language: lang === "en" ? "hi" : "en" })}
            testId="language"
          >
            {lang === "en" ? "हिंदी" : "English"}
          </Button>
          {allowed.includes("staff_assist") ? (
            <Button variant="secondary" onClick={() => send("staff_assist")} testId="call-staff">
              🙋 {t.callStaff}
            </Button>
          ) : null}
        </div>
      </footer>
    </div>
  );
}

export function Keypad({ onKey, keys }: { onKey: (k: string) => void; keys?: string[] }) {
  const layout = keys ?? ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "✓"];
  return (
    <div className="grid grid-cols-3 gap-4">
      {layout.map((k) => (
        <button
          key={k}
          type="button"
          data-testid={`key-${k}`}
          onClick={() => onKey(k)}
          className="h-20 rounded-2xl border border-arena-600 bg-arena-800 font-display text-4xl active:bg-arena-600"
        >
          {k}
        </button>
      ))}
    </div>
  );
}

const ROWS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];

export function AlphaKeyboard({ value, onChange, max = 60 }: { value: string; onChange: (v: string) => void; max?: number }) {
  const press = (ch: string) => onChange((value + ch).slice(0, max));
  return (
    <div className="flex flex-col gap-3">
      {ROWS.map((row) => (
        <div key={row} className="flex justify-center gap-3">
          {row.split("").map((ch) => (
            <button
              key={ch}
              type="button"
              data-testid={`kb-${ch}`}
              onClick={() => press(value.length === 0 || value.endsWith(" ") ? ch : ch.toLowerCase())}
              className="h-16 w-16 rounded-xl border border-arena-600 bg-arena-800 text-2xl font-semibold active:bg-arena-600"
            >
              {ch}
            </button>
          ))}
        </div>
      ))}
      <div className="flex justify-center gap-3">
        <button type="button" onClick={() => press("'")} className="h-16 w-16 rounded-xl border border-arena-600 bg-arena-800 text-2xl">
          '
        </button>
        <button
          type="button"
          data-testid="kb-space"
          onClick={() => press(" ")}
          className="h-16 w-96 rounded-xl border border-arena-600 bg-arena-800 text-xl text-ink-muted"
        >
          space
        </button>
        <button
          type="button"
          data-testid="kb-backspace"
          onClick={() => onChange(value.slice(0, -1))}
          className="h-16 w-28 rounded-xl border border-arena-600 bg-arena-800 text-2xl"
        >
          ⌫
        </button>
      </div>
    </div>
  );
}

export function Countdown({ until, onExpire }: { until: string; onExpire?: () => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, []);
  const left = Math.max(0, Math.floor((new Date(until).getTime() - now) / 1000));
  useEffect(() => {
    if (left === 0) onExpire?.();
  }, [left, onExpire]);
  const mm = String(Math.floor(left / 60)).padStart(1, "0");
  const ss = String(left % 60).padStart(2, "0");
  return (
    <span data-testid="countdown" className={`font-display ${left <= 60 ? "text-alert" : "text-laser"}`}>
      {mm}:{ss}
    </span>
  );
}

function VoiceCaption() {
  const voice = useKiosk((s) => s.voice);
  if (voice.status === "off" || voice.status === "unavailable" || !voice.caption) return null;
  return (
    <p data-testid="voice-caption" className={`text-2xl ${voice.caption.role === "user" ? "text-ink-muted italic" : "text-laser"}`}>
      {voice.caption.role === "user" ? "🎤 " : ""}
      {voice.caption.text}
    </p>
  );
}

function MicToggle() {
  const voice = useKiosk((s) => s.voice);
  const setVoice = useKiosk((s) => s.setVoice);
  if (voice.status === "off" || voice.status === "unavailable") return null;
  return (
    <button
      type="button"
      data-testid="mic-toggle"
      onClick={() => setVoice({ muted: !voice.muted })}
      className={`min-h-[72px] rounded-2xl border px-6 text-[26px] ${voice.muted ? "border-alert text-alert" : "border-signal text-signal"}`}
      aria-label={voice.muted ? "Unmute microphone" : "Mute microphone"}
    >
      {voice.muted ? "🔇" : "🎤"}
    </button>
  );
}
