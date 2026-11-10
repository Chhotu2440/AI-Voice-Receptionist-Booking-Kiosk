import { Button, Countdown, Screen, Tile } from "../components/ui";
import { OCCASION_LABELS, formatDate, inr } from "../i18n";
import { useKiosk, useT } from "../store";

export function PackagesScreen() {
  const { t, lang } = useT();
  const send = useKiosk((s) => s.send);
  const st = useKiosk((s) => s.state);
  const packages = st?.packages ?? [];
  return (
    <Screen prompt={t.packagesTitle}>
      <div className="grid grid-cols-3 gap-6">
        {packages.map((p) => (
          <div
            key={p.id}
            data-testid={`package-${p.code}`}
            className={`relative flex flex-col gap-4 rounded-3xl border bg-arena-800 p-7 ${
              p.recommended ? "border-plasma shadow-plasma" : "border-arena-600"
            } ${p.eligible ? "" : "opacity-40"}`}
          >
            {p.recommended ? (
              <span className="absolute -top-4 left-6 rounded-full bg-plasma px-4 py-1 text-lg font-bold text-arena-950">
                {t.recommended}
              </span>
            ) : null}
            <div className="font-display text-4xl">{lang === "hi" ? p.name_hi : p.name_en}</div>
            <div className="text-2xl text-ink-muted">
              {p.duration_min} {t.minutes}
              {p.games_count ? ` · ${p.games_count} ${t.games}` : ""}
              {p.formats_count ? ` · ${p.formats_count} ${t.formats}` : ""}
            </div>
            <ul className="flex-1 space-y-1 text-xl">
              {p.features.map((f) => (
                <li key={f.en}>• {f[lang]}</li>
              ))}
            </ul>
            <div>
              <div className="text-lg text-ink-muted">{t.todayPrice}</div>
              <div className="font-display text-4xl text-laser">
                {inr(p.price_per_person)} <span className="text-xl text-ink-muted">{t.perPerson}</span>
              </div>
              {p.estimated_total ? (
                <div className="text-xl text-ink-muted">
                  {t.estTotal}: {inr(p.estimated_total)}
                </div>
              ) : null}
            </div>
            {p.eligible ? (
              <Button onClick={() => send("select_package", { package_id: p.id })} testId={`choose-${p.code}`}>
                {t.choose}
              </Button>
            ) : (
              <div className="text-xl text-alert">{t.notForGroup}</div>
            )}
          </div>
        ))}
      </div>
    </Screen>
  );
}

export function DateScreen() {
  const { t, lang } = useT();
  const send = useKiosk((s) => s.send);
  const st = useKiosk((s) => s.state);
  const dates = st?.available_dates ?? [];
  return (
    <Screen prompt={t.askDate}>
      <div className="grid grid-cols-7 gap-4">
        {dates.map((d, i) => {
          const label = i === 0 ? t.today : i === 1 ? t.tomorrow : formatDate(d.date, lang, { weekday: "short" });
          const usable = d.status === "OPEN";
          return (
            <Tile key={d.date} testId={`date-${d.date}`} disabled={!usable} selected={st?.play_date === d.date} onClick={() => send("select_date", { date: d.date })} className="h-36 text-center">
              <div className="text-xl text-ink-muted">{label}</div>
              <div className="mt-1 font-display text-3xl">{formatDate(d.date, lang, { weekday: undefined })}</div>
              <div className={`mt-2 text-lg ${usable ? "text-signal" : "text-alert"}`}>
                {d.status === "CLOSED" ? d.closed_reason || t.closed : d.status === "FULL" ? t.full : `${d.slots_available} ${t.slotsLeft}`}
              </div>
            </Tile>
          );
        })}
      </div>
    </Screen>
  );
}

export function SlotsScreen() {
  const { t, lang } = useT();
  const send = useKiosk((s) => s.send);
  const st = useKiosk((s) => s.state);
  const slots = st?.slots ?? [];
  return (
    <Screen prompt={t.askTime} sub={st?.play_date ? formatDate(st.play_date, lang, { weekday: "long" }) : undefined}>
      {slots.length === 0 ? (
        <div className="flex flex-col items-center gap-8 text-3xl">
          <p data-testid="no-slots">{t.noSlots}</p>
          <Button onClick={() => send("back")}>{t.otherDate}</Button>
        </div>
      ) : (
        <div className="grid grid-cols-5 gap-4">
          {slots.map((s) => (
            <Tile key={s.start_time} testId={`slot-${s.start_time}`} onClick={() => send("select_slot", { start_time: s.start_time })} className="h-28 text-center">
              <div className="font-display text-4xl">{s.start_time}</div>
              <div className="text-lg text-ink-muted">→ {s.end_time}</div>
            </Tile>
          ))}
        </div>
      )}
    </Screen>
  );
}

function Row({ label, value, field }: { label: string; value: string; field?: string }) {
  const { t } = useT();
  const send = useKiosk((s) => s.send);
  return (
    <div className="flex items-center justify-between border-b border-arena-700 py-3 text-2xl">
      <span className="text-ink-muted">{label}</span>
      <span className="flex items-center gap-4">
        <span className="font-semibold">{value}</span>
        {field ? (
          <button type="button" data-testid={`edit-${field}`} onClick={() => send("edit", { field })} className="rounded-lg px-3 py-1 text-lg text-laser underline">
            {t.edit}
          </button>
        ) : null}
      </span>
    </div>
  );
}

export function SummaryScreen() {
  const { t, lang } = useT();
  const send = useKiosk((s) => s.send);
  const st = useKiosk((s) => s.state);
  if (!st?.quote) return null;
  const q = st.quote;
  const pkg = st.packages.find((p) => p.id === st.package_id);
  return (
    <Screen prompt={t.summaryTitle}>
      <div className="grid grid-cols-2 gap-10">
        <div>
          <Row label={t.name} value={st.customer_name ?? ""} field="name" />
          <Row label={t.mobile} value={st.phone_display ?? ""} field="phone" />
          <Row label={t.guests} value={String(st.guest_count)} field="guests" />
          <Row label={t.occasion} value={OCCASION_LABELS[st.occasion_code ?? ""]?.[lang] ?? ""} field="occasion" />
          <Row label={t.package} value={pkg ? (lang === "hi" ? pkg.name_hi : pkg.name_en) : ""} field="package" />
          <Row label={t.date} value={st.play_date ? formatDate(st.play_date, lang, { weekday: "long" }) : ""} field="date" />
          <Row label={t.time} value={st.start_time ?? ""} field="slot" />
        </div>
        <div className="flex flex-col gap-3 rounded-3xl border border-arena-600 bg-arena-800 p-7 text-2xl">
          <div className="flex justify-between">
            <span>
              {t.pricePerPerson} × {q.guest_count}
            </span>
            <span>{inr(q.price_per_person)}</span>
          </div>
          <div className="flex justify-between">
            <span>{t.subtotal}</span>
            <span>{inr(q.subtotal)}</span>
          </div>
          {q.discounts.map((d) => (
            <div key={d.name} className="flex justify-between text-signal">
              <span>{d.name || t.discount}</span>
              <span>−{inr(d.amount)}</span>
            </div>
          ))}
          {q.charges.map((c) => (
            <div key={c.code} className="flex justify-between">
              <span>{c.label}</span>
              <span>{inr(c.amount)}</span>
            </div>
          ))}
          <div className="flex justify-between text-xl text-ink-muted">
            <span>
              {t.tax} {Number(q.tax.rate)}% {q.tax.included ? `(${t.taxIncluded})` : ""}
            </span>
            <span>{inr(q.tax.amount)}</span>
          </div>
          <div className="mt-2 flex justify-between border-t border-arena-600 pt-4 font-display text-4xl text-laser">
            <span>{t.total}</span>
            <span data-testid="total">{inr(q.total)}</span>
          </div>
          <div className="text-xl text-ink-muted">{t.payAtReception}</div>
          <label className="mt-2 flex items-center gap-4">
            <input
              type="checkbox"
              data-testid="whatsapp-consent"
              className="h-8 w-8 accent-laser"
              checked={st.whatsapp_consent}
              onChange={(e) => send("set_consent", { whatsapp: e.target.checked })}
            />
            {t.whatsappConsent}
          </label>
          {st.hold_expires_at ? (
            <div className="flex items-center justify-between text-xl">
              <span>
                {t.holdEndsIn} <Countdown until={st.hold_expires_at} />
              </span>
              {st.hold_can_extend ? (
                <button type="button" onClick={() => send("extend_hold")} className="text-laser underline">
                  {t.extend}
                </button>
              ) : null}
            </div>
          ) : null}
          <Button onClick={() => send("confirm_booking")} testId="confirm-booking" className="mt-2 text-3xl">
            ✓ {t.confirmBooking}
          </Button>
        </div>
      </div>
    </Screen>
  );
}
