import { useState } from "react";

import { AlphaKeyboard, Button, Keypad, Screen } from "../components/ui";
import { useKiosk, useT } from "../store";

export function NameScreen() {
  const { t } = useT();
  const send = useKiosk((s) => s.send);
  const current = useKiosk((s) => s.state?.customer_name ?? "");
  const [name, setName] = useState(current);
  return (
    <Screen prompt={t.askName}>
      <div className="flex flex-col items-center gap-6">
        <div
          data-testid="name-value"
          className="min-h-[88px] w-full max-w-3xl rounded-2xl border-2 border-laser bg-arena-800 px-8 py-4 text-center text-5xl"
        >
          {name || <span className="text-ink-muted">{t.yourName}</span>}
        </div>
        <AlphaKeyboard value={name} onChange={setName} />
        <Button onClick={() => send("set_name", { name })} disabled={!name.trim()} testId="name-next">
          {t.continueHere} →
        </Button>
      </div>
    </Screen>
  );
}

export function PhoneScreen() {
  const { t } = useT();
  const send = useKiosk((s) => s.send);
  const st = useKiosk((s) => s.state);
  const [digits, setDigits] = useState("");
  const [editing, setEditing] = useState(false);
  const entered = st?.phone_display && !st.phone_confirmed && !editing;

  if (entered) {
    return (
      <Screen prompt={t.isThisRight}>
        <div className="flex flex-col items-center gap-10">
          <div data-testid="phone-readback" className="font-display text-7xl tracking-widest text-laser">
            {st.phone_display}
          </div>
          <div className="flex gap-6">
            <Button
              variant="secondary"
              onClick={() => {
                setDigits("");
                setEditing(true);
              }}
              testId="phone-edit"
            >
              {t.edit}
            </Button>
            <Button onClick={() => send("confirm_phone")} testId="phone-confirm">
              ✓ {t.yesCorrect}
            </Button>
          </div>
        </div>
      </Screen>
    );
  }

  const onKey = (k: string) => {
    if (k === "⌫") setDigits((d) => d.slice(0, -1));
    else if (k === "✓") {
      setEditing(false);
      send("set_phone", { phone: digits });
    }
    else setDigits((d) => (d + k).slice(0, 10));
  };
  const shown = digits.length > 5 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : digits;
  return (
    <Screen prompt={t.askPhone}>
      <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
        <div
          data-testid="phone-value"
          className="min-h-[96px] rounded-2xl border-2 border-laser bg-arena-800 px-8 py-4 text-center font-display text-6xl tracking-widest"
        >
          <span className="text-ink-muted">+91 </span>
          {shown}
        </div>
        <Keypad onKey={onKey} />
      </div>
    </Screen>
  );
}
