import { QRCodeSVG } from "qrcode.react";
import { useEffect } from "react";

import { Assistant, Button } from "../components/ui";
import { formatDate, inr } from "../i18n";
import { useKiosk, useT } from "../store";

function useAutoFinish(seconds: number) {
  const send = useKiosk((s) => s.send);
  useEffect(() => {
    const id = window.setTimeout(() => send("finish"), seconds * 1000);
    return () => window.clearTimeout(id);
  }, [send, seconds]);
}

export function ConfirmedScreen() {
  const { t, lang } = useT();
  const send = useKiosk((s) => s.send);
  const booking = useKiosk((s) => s.state?.booking);
  const resetAfter = useKiosk((s) => s.config.success_reset_s);
  useAutoFinish(resetAfter);
  if (!booking) return null;
  return (
    <div className="relative flex h-full flex-col items-center justify-center gap-8 overflow-hidden px-10">
      <div className="pointer-events-none absolute inset-x-0 top-1/2 h-1 overflow-hidden">
        <div className="h-full w-1/2 animate-sweep bg-gradient-to-r from-transparent via-signal to-transparent" />
      </div>
      <div className="font-display text-6xl text-signal" data-testid="confirmed-title">
        ✓ {t.confirmedTitle}
      </div>
      <p className="text-3xl">{t.confirmedLine}</p>
      <div className="flex items-center gap-12 rounded-3xl border border-arena-600 bg-arena-800 p-10">
        <div className="rounded-xl bg-white p-4">
          <QRCodeSVG value={booking.reference} size={200} />
        </div>
        <div className="flex flex-col gap-3 text-2xl">
          <div className="text-ink-muted">{t.bookingRef}</div>
          <div data-testid="booking-reference" className="font-display text-6xl tracking-widest text-laser">
            {booking.reference}
          </div>
          <div>
            {booking.package_name} · {booking.guest_count} {t.players}
          </div>
          <div>
            {formatDate(booking.date, lang, { weekday: "long" })} · {booking.start_time}–{booking.end_time}
          </div>
          <div className="font-display text-3xl">
            {t.total}: {inr(booking.pricing.total)}
          </div>
          <div className="text-ink-muted">{t.payAtReception}</div>
        </div>
      </div>
      <p className="text-2xl text-ink-muted">{t.showAtDesk}</p>
      <Button onClick={() => send("finish")} testId="done">
        {t.done}
      </Button>
    </div>
  );
}

export function EnquiryDoneScreen() {
  const { t } = useT();
  const send = useKiosk((s) => s.send);
  const ref = useKiosk((s) => s.state?.enquiry_reference);
  const resetAfter = useKiosk((s) => s.config.success_reset_s);
  useAutoFinish(resetAfter);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-8">
      <Assistant />
      <div className="font-display text-5xl text-signal">{t.enquirySent}</div>
      <div className="text-2xl text-ink-muted">{t.enquiryRef}</div>
      <div data-testid="enquiry-reference" className="font-display text-6xl tracking-widest text-laser">
        {ref}
      </div>
      <Button onClick={() => send("finish")}>{t.done}</Button>
    </div>
  );
}

export function StaffScreen() {
  const { t } = useT();
  const send = useKiosk((s) => s.send);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-8">
      <Assistant />
      <div className="font-display text-5xl text-laser">{t.staffTitle}</div>
      <p className="text-3xl text-ink-muted">{t.staffLine}</p>
      <div className="flex gap-6">
        <Button variant="secondary" onClick={() => send("cancel")}>
          {t.startOver}
        </Button>
        <Button onClick={() => send("staff_resume")} testId="staff-resume">
          {t.continueHere}
        </Button>
      </div>
    </div>
  );
}

export function CancelledScreen() {
  const { t } = useT();
  useAutoFinish(4);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6">
      <Assistant />
      <div className="font-display text-5xl text-laser">{t.cancelledTitle}</div>
      <p className="text-3xl text-ink-muted">{t.cancelledLine}</p>
    </div>
  );
}
