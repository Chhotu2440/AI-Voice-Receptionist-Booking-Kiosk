import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { DaySlots } from "../lib/types";
import { ErrorBox, Loading } from "./ui";

/** Live availability for one package/date/group size; the backend decides what is bookable. */
export function SlotPicker({
  packageId,
  date,
  guests,
  value,
  onChange,
}: {
  packageId: string;
  date: string;
  guests: number;
  value: string | null;
  onChange: (start: string | null) => void;
}) {
  const enabled = !!packageId && !!date && guests > 0;
  const q = useQuery({
    queryKey: ["slots", packageId, date, guests],
    queryFn: () =>
      api<DaySlots>("/availability/slots", {
        method: "POST",
        body: { package_id: packageId, date, guest_count: guests },
      }),
    enabled,
    staleTime: 5_000,
  });
  if (!enabled) return <p className="text-sm text-slate-500">Choose a package, date and group size first.</p>;
  if (q.isPending) return <Loading label="Checking availability…" />;
  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.data.status === "CLOSED")
    return <p className="text-sm text-amber-600">Closed that day{q.data.closed_reason ? `: ${q.data.closed_reason}` : ""}.</p>;
  if (q.data.slots.length === 0) return <p className="text-sm text-amber-600">No free slots that day.</p>;
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-5" role="radiogroup" aria-label="Start time">
      {q.data.slots.map((s) => (
        <button
          type="button"
          key={s.start_time}
          role="radio"
          aria-checked={value === s.start_time}
          data-testid={`slot-${s.start_time}`}
          onClick={() => onChange(value === s.start_time ? null : s.start_time)}
          className={`rounded-lg border px-2 py-2 text-sm tabular-nums transition ${
            value === s.start_time
              ? "border-brand-600 bg-brand-600 text-white"
              : "border-slate-300 hover:border-brand-500 dark:border-slate-700"
          }`}
        >
          {s.start_time}
        </button>
      ))}
    </div>
  );
}
