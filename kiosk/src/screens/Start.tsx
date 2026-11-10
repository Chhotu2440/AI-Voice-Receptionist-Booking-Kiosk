import { useState } from "react";

import { AlphaKeyboard, Assistant, Button, Keypad, Screen } from "../components/ui";
import { ApiError, pairDevice } from "../lib/api";
import { useKiosk, useT } from "../store";

export function Setup({ onPaired }: { onPaired: () => void }) {
  const { t } = useT();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await pairDevice(code);
      onPaired();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col items-center justify-center gap-8">
      <h1 className="font-display text-5xl text-laser">{t.setupTitle}</h1>
      <p className="text-2xl text-ink-muted">{t.setupLine}</p>
      <div data-testid="pair-code" className="min-h-[88px] min-w-[420px] rounded-2xl border-2 border-laser bg-arena-800 px-8 py-4 text-center font-display text-5xl tracking-[0.3em]">
        {code || "—"}
      </div>
      <AlphaKeyboard value={code} onChange={(v) => setCode(v.toUpperCase().replace(/[^A-Z0-9-]/g, ""))} max={9} />
      <Keypad keys={["2", "3", "4", "5", "6", "7", "8", "9", "-"]} onKey={(k) => setCode((c) => (c + k).slice(0, 9))} />
      {error ? <p role="alert" className="text-2xl text-alert">{error}</p> : null}
      <button
        type="button"
        data-testid="pair-submit"
        disabled={busy || code.replace("-", "").length < 8}
        onClick={() => void submit()}
        className="min-h-[72px] rounded-2xl bg-laser px-10 text-[26px] font-semibold text-arena-950 shadow-laser disabled:opacity-40"
      >
        {t.pair}
      </button>
    </div>
  );
}

export function Idle() {
  const { t } = useT();
  const send = useKiosk((s) => s.send);
  // Ready only once the server state has arrived; a tap before that would otherwise be lost.
  const ready = useKiosk((s) => s.conn === "online" && s.allowed.includes("start") && s.pending === null);
  return (
    <button
      type="button"
      data-testid="tap-to-start"
      disabled={!ready}
      onClick={() => send("start")}
      className="relative flex h-full w-full flex-col items-center justify-center gap-10 overflow-hidden"
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(34,228,255,0.14),transparent_60%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-1/3 h-[2px] overflow-hidden">
        <div className="h-full w-1/2 animate-sweep bg-gradient-to-r from-transparent via-plasma to-transparent [animation-iteration-count:infinite]" />
      </div>
      <div className="font-display text-[88px] leading-none tracking-widest text-laser drop-shadow-[0_0_24px_rgba(34,228,255,0.5)]">
        PLAY LASER TAG
      </div>
      <Assistant />
      <div className="rounded-full bg-laser px-16 py-6 font-display text-4xl text-arena-950 shadow-laser animate-breathe">
        {t.tapToStart}
      </div>
      <p className="absolute bottom-8 text-xl text-ink-muted">{t.privacy}</p>
    </button>
  );
}

export function Greeting() {
  const { t } = useT();
  const send = useKiosk((s) => s.send);
  return (
    <Screen prompt={t.welcome} sub={t.greeting}>
      <div className="flex justify-center">
        <Button onClick={() => send("continue")} testId="lets-go" className="px-16 text-4xl">
          {t.letsGo} →
        </Button>
      </div>
    </Screen>
  );
}
