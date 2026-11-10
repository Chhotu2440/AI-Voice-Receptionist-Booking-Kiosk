import { useState } from "react";

import { AlphaKeyboard, Button, Screen, Tile } from "../components/ui";
import { OCCASION_LABELS, formatDate } from "../i18n";
import { useKiosk, useT } from "../store";

const CHIPS = [1, 2, 3, 4, 5, 6, 8, 10, 12];

export function GuestsScreen() {
  const { t } = useT();
  const send = useKiosk((s) => s.send);
  const current = useKiosk((s) => s.state?.guest_count ?? null);
  const [custom, setCustom] = useState<number | null>(null);
  if (custom !== null) {
    return (
      <Screen prompt={t.askGuests}>
        <div className="flex flex-col items-center gap-10">
          <div className="flex items-center gap-10">
            <Button variant="secondary" onClick={() => setCustom(Math.max(1, custom - 1))} testId="guests-minus" className="w-24 text-5xl">
              −
            </Button>
            <div data-testid="guests-value" className="w-48 text-center font-display text-8xl text-laser">
              {custom}
            </div>
            <Button variant="secondary" onClick={() => setCustom(Math.min(200, custom + 1))} testId="guests-plus" className="w-24 text-5xl">
              +
            </Button>
          </div>
          <Button onClick={() => send("set_guests", { count: custom })} testId="guests-next">
            {custom} {t.players} →
          </Button>
        </div>
      </Screen>
    );
  }
  return (
    <Screen prompt={t.askGuests}>
      <div className="grid grid-cols-5 gap-5">
        {CHIPS.map((n) => (
          <Tile key={n} testId={`guests-${n}`} selected={current === n} onClick={() => send("set_guests", { count: n })} className="h-32 text-center">
            <div className="font-display text-5xl">{n}</div>
          </Tile>
        ))}
        <Tile testId="guests-more" onClick={() => setCustom(Math.max(13, current ?? 13))} className="h-32 text-center">
          <div className="font-display text-3xl">{t.more}…</div>
        </Tile>
      </div>
    </Screen>
  );
}

export function OccasionScreen() {
  const { t, lang } = useT();
  const send = useKiosk((s) => s.send);
  const current = useKiosk((s) => s.state?.occasion_code);
  return (
    <Screen prompt={t.askOccasion}>
      <div className="grid grid-cols-3 gap-5">
        {Object.entries(OCCASION_LABELS).map(([code, label]) => (
          <Tile key={code} testId={`occasion-${code}`} selected={current === code} onClick={() => send("set_occasion", { code })} className="h-44">
            <div className="text-5xl">{label.icon}</div>
            <div className="mt-4 text-3xl font-semibold">{label[lang]}</div>
          </Tile>
        ))}
      </div>
    </Screen>
  );
}

export function CustomEventScreen() {
  const { t, lang } = useT();
  const send = useKiosk((s) => s.send);
  const occasion = useKiosk((s) => s.state?.occasion_code ?? "OTHER");
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState<string | null>(null);
  const [whatsapp, setWhatsapp] = useState(false);
  const days = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i + 1);
    return d.toLocaleDateString("en-CA");
  });
  return (
    <Screen prompt={t.enquiryTitle} sub={t.enquiryIntro}>
      <div className="flex flex-col gap-6">
        <div className="text-2xl text-ink-muted">
          {OCCASION_LABELS[occasion]?.[lang]} · {t.preferredDate}
        </div>
        <div className="flex flex-wrap gap-3">
          {days.map((d) => (
            <Tile key={d} selected={date === d} onClick={() => setDate(date === d ? null : d)} className="px-4 py-3 text-xl">
              {formatDate(d, lang)}
            </Tile>
          ))}
        </div>
        <div className="text-2xl text-ink-muted">{t.requirements}</div>
        <div className="min-h-[72px] rounded-2xl border border-arena-600 bg-arena-800 px-6 py-4 text-3xl">{notes}</div>
        <AlphaKeyboard value={notes} onChange={setNotes} max={200} />
        <label className="flex items-center gap-4 text-2xl">
          <input type="checkbox" className="h-8 w-8 accent-laser" checked={whatsapp} onChange={(e) => setWhatsapp(e.target.checked)} />
          {t.whatsappConsent}
        </label>
        <Button
          testId="send-enquiry"
          onClick={() =>
            send("submit_enquiry", {
              preferred_date: date,
              details: notes.trim() ? { special_requirements: notes.trim() } : {},
              whatsapp,
            })
          }
        >
          {t.sendEnquiry} →
        </Button>
      </div>
    </Screen>
  );
}
