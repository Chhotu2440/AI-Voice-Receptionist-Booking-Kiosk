import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Empty, ErrorBox, Loading, Modal, PageHeader } from "../components/ui";
import { api, qs } from "../lib/api";
import { useAuth } from "../lib/auth";
import { addDays, dateLabel, todayIST } from "../lib/format";
import type { Booking, BookingSettings, BusinessInfo, HoursDay, Page, Resource, ScheduleException } from "../lib/types";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const EXC_LABEL: Record<ScheduleException["type"], { label: string; help: string }> = {
  HOLIDAY: { label: "Closed all day", help: "Holiday or private closure: no bookings that day" },
  SPECIAL_HOURS: { label: "Special opening hours", help: "Open, but with different hours that day" },
  MANUAL_BLOCK: { label: "Block some hours", help: "e.g. maintenance or a private event, 2–4 pm" },
  BLACKOUT: { label: "Blackout", help: "No online/kiosk bookings (whole day, or between times)" },
};
const hhmm = (t: string | null) => (t ? t.slice(0, 5) : "");

export function SchedulePage() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader title="Schedule" subtitle="Opening hours, closures and blocks, the arena, and booking rules. Changes apply to the kiosk immediately." />
      <div className="space-y-6">
        <ExceptionsSection editable={can("schedule.write")} />
        <HoursSection editable={can("schedule.write")} />
        <ResourcesSection editable={can("schedule.write")} />
        <BookingRulesSection editable={can("settings.write")} />
        <BusinessInfoSection editable={can("settings.write")} />
      </div>
    </>
  );
}

function HoursSection({ editable }: { editable: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["hours"], queryFn: () => api<HoursDay[]>("/admin/schedule/hours") });
  const [days, setDays] = useState<HoursDay[] | null>(null);
  useEffect(() => {
    if (q.data) setDays([...q.data].sort((a, b) => a.weekday - b.weekday).map((d) => ({ ...d, open_time: hhmm(d.open_time), close_time: hhmm(d.close_time) })));
  }, [q.data]);
  const m = useMutation({
    mutationFn: () => api<HoursDay[]>("/admin/schedule/hours", { method: "PUT", body: { days } }),
    onSuccess: (data) => qc.setQueryData(["hours"], data),
  });
  if (q.isPending || !days) return <div className="card"><Loading /></div>;
  if (q.isError) return <ErrorBox error={q.error} />;
  const set = (i: number, patch: Partial<HoursDay>) => setDays(days.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const copyMonday = () => setDays(days.map((d) => ({ ...d, open_time: days[0]!.open_time, close_time: days[0]!.close_time, is_closed: days[0]!.is_closed })));

  return (
    <section className="card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">Weekly opening hours</h2>
          <p className="text-sm text-slate-500">The last game must finish by closing time.</p>
        </div>
        {editable && <button type="button" className="btn-secondary" onClick={copyMonday}>Copy Monday to all days</button>}
      </div>
      <fieldset disabled={!editable} className="divide-y divide-slate-100 dark:divide-slate-800">
        {days.map((d, i) => (
          <div key={d.weekday} className="flex flex-wrap items-center gap-3 py-2 text-sm">
            <span className="w-28 font-medium">{WEEKDAYS[d.weekday]}</span>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={!d.is_closed} onChange={(e) => set(i, { is_closed: !e.target.checked })} />
              Open
            </label>
            {d.is_closed ? (
              <span className="text-slate-500">Closed</span>
            ) : (
              <span className="flex items-center gap-2">
                <input aria-label={`${WEEKDAYS[d.weekday]} opens`} type="time" className="input w-32" value={d.open_time} onChange={(e) => set(i, { open_time: e.target.value })} />
                <span>to</span>
                <input aria-label={`${WEEKDAYS[d.weekday]} closes`} type="time" className="input w-32" value={d.close_time} onChange={(e) => set(i, { close_time: e.target.value })} />
              </span>
            )}
          </div>
        ))}
      </fieldset>
      {editable && (
        <div className="mt-3 flex items-center justify-end gap-3">
          <ErrorBox error={m.error} />
          {m.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
          <button className="btn-primary" disabled={m.isPending} onClick={() => m.mutate()}>Save hours</button>
        </div>
      )}
    </section>
  );
}

function ExceptionsSection({ editable }: { editable: boolean }) {
  const qc = useQueryClient();
  const from = todayIST();
  const to = addDays(from, 180);
  const q = useQuery({
    queryKey: ["exceptions", from, to],
    queryFn: () => api<ScheduleException[]>(`/admin/schedule/exceptions${qs({ from, to })}`),
  });
  const resources = useQuery({ queryKey: ["resources"], queryFn: () => api<Resource[]>("/admin/resources") });
  const [adding, setAdding] = useState(false);
  const del = useMutation({
    mutationFn: (id: string) => api(`/admin/schedule/exceptions/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["exceptions"] }),
  });
  const resourceName = (id: string | null) => (id ? resources.data?.find((r) => r.id === id)?.name ?? "Arena" : "Whole venue");

  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div>
          <h2 className="font-semibold">Holidays, special hours &amp; blocks</h2>
          <p className="text-sm text-slate-500">Next 6 months.</p>
        </div>
        {editable && <button className="btn-primary" onClick={() => setAdding(true)} data-testid="add-exception">+ Add closure or block</button>}
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <div className="p-4"><ErrorBox error={q.error} /></div>
      ) : q.data.length === 0 ? (
        <Empty>Normal hours every day.</Empty>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {q.data.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm" data-testid={`exception-${e.date}`}>
              <div>
                <span className="font-medium">{dateLabel(e.date)}</span> · {EXC_LABEL[e.type].label}
                {e.start_time && ` ${hhmm(e.start_time)}–${hhmm(e.end_time)}`}
                <span className="text-slate-500"> · {resourceName(e.resource_id)}{e.reason && ` · ${e.reason}`}</span>
              </div>
              {editable && (
                <button className="btn-secondary" disabled={del.isPending} onClick={() => del.mutate(e.id)}>Remove</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {del.isError && <div className="p-4"><ErrorBox error={del.error} /></div>}
      {adding && <ExceptionModal resources={resources.data ?? []} onClose={() => setAdding(false)} />}
    </section>
  );
}

function ExceptionModal({ resources, onClose }: { resources: Resource[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState<ScheduleException["type"]>("HOLIDAY");
  const [date, setDate] = useState(todayIST());
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [resource, setResource] = useState("");
  const [reason, setReason] = useState("");
  const needsTimes = type === "SPECIAL_HOURS" || type === "MANUAL_BLOCK";
  const allowsTimes = needsTimes || type === "BLACKOUT";

  // Existing bookings are never cancelled automatically: show staff who is affected before they save.
  const affected = useQuery({
    queryKey: ["bookings-on", date],
    queryFn: () => api<Page<Booking>>(`/admin/bookings${qs({ from: date, to: date, status: ["CONFIRMED"], page_size: 100 })}`),
    enabled: !!date,
  });
  const clash = (affected.data?.items ?? []).filter((b) => {
    if (type === "SPECIAL_HOURS") return !!start && !!end && (b.start_time < start || b.end_time > end);
    if (start && end) return b.start_time < end && b.end_time > start;
    return true;
  });

  const m = useMutation({
    mutationFn: () =>
      api("/admin/schedule/exceptions", {
        method: "POST",
        body: {
          type,
          date,
          start_time: allowsTimes && start ? start : null,
          end_time: allowsTimes && end ? end : null,
          resource_id: resource || null,
          reason: reason.trim(),
        },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["exceptions"] });
      onClose();
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    m.mutate();
  }

  return (
    <Modal open onClose={onClose} title="Add closure or block">
      <form className="space-y-3 text-sm" onSubmit={submit}>
        <div className="space-y-1.5">
          {(Object.keys(EXC_LABEL) as ScheduleException["type"][]).map((t) => (
            <label key={t} className={`flex cursor-pointer gap-2 rounded-lg border p-2 ${type === t ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20" : "border-slate-200 dark:border-slate-700"}`}>
              <input type="radio" name="exc-type" className="mt-0.5 accent-brand-600" checked={type === t} onChange={() => setType(t)} />
              <span><span className="font-medium">{EXC_LABEL[t].label}</span><span className="block text-xs text-slate-500">{EXC_LABEL[t].help}</span></span>
            </label>
          ))}
        </div>
        <div>
          <label className="label" htmlFor="ex-date">Date</label>
          <input id="ex-date" type="date" className="input" min={todayIST()} required value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        {allowsTimes && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="ex-start">{type === "SPECIAL_HOURS" ? "Opens" : "From"}</label>
              <input id="ex-start" type="time" className="input" required={needsTimes} value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="ex-end">{type === "SPECIAL_HOURS" ? "Closes" : "Until"}</label>
              <input id="ex-end" type="time" className="input" required={needsTimes} value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
        )}
        {resources.length > 1 && (
          <div>
            <label className="label" htmlFor="ex-res">Applies to</label>
            <select id="ex-res" className="input" value={resource} onChange={(e) => setResource(e.target.value)}>
              <option value="">Whole venue</option>
              {resources.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </div>
        )}
        <div>
          <label className="label" htmlFor="ex-reason">Reason (staff only)</label>
          <input id="ex-reason" className="input" maxLength={255} placeholder="e.g. Diwali" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        {clash.length > 0 && (
          <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200" data-testid="exception-clash">
            <strong>{clash.length} confirmed booking{clash.length > 1 ? "s" : ""}</strong> already in this time. They are <strong>not</strong> cancelled
            automatically. Call the customers, then cancel or move them in{" "}
            <Link className="underline" to={`/bookings`}>Bookings</Link>:
            <ul className="mt-1 list-disc pl-5">
              {clash.map((b) => <li key={b.id}>{b.start_time} · {b.customer.name} · {b.reference}</li>)}
            </ul>
          </div>
        )}
        <ErrorBox error={m.error} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={m.isPending} data-testid="save-exception">Save</button>
        </div>
      </form>
    </Modal>
  );
}

function ResourcesSection({ editable }: { editable: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["resources"], queryFn: () => api<Resource[]>("/admin/resources") });
  const [edit, setEdit] = useState<Resource | null>(null);
  return (
    <section className="card overflow-hidden">
      <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 className="font-semibold">Arena &amp; time slots</h2>
        <p className="text-sm text-slate-500">How often games can start, the gap between groups, and how many players fit.</p>
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <div className="p-4"><ErrorBox error={q.error} /></div>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {q.data.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
              <div>
                <div className="font-medium">{r.name}{!r.is_active && <span className="ml-2 text-xs text-slate-500">(not in use)</span>}</div>
                <div className="text-slate-500">
                  {r.capacity_mode === "EXCLUSIVE" ? "One group at a time" : `Shared: ${r.default_capacity} places per slot`} · up to {r.max_players} players ·
                  a game can start every {r.slot_interval_min} min · {r.buffer_min} min gap between groups
                </div>
              </div>
              {editable && <button className="btn-secondary" onClick={() => setEdit(r)}>Edit</button>}
            </li>
          ))}
        </ul>
      )}
      {edit && <ResourceModal resource={edit} onClose={() => setEdit(null)} onSaved={() => void qc.invalidateQueries({ queryKey: ["resources"] })} />}
    </section>
  );
}

function ResourceModal({ resource, onClose, onSaved }: { resource: Resource; onClose: () => void; onSaved: () => void }) {
  const [r, setR] = useState(resource);
  const m = useMutation({
    mutationFn: () => {
      const body = Object.fromEntries(
        (["name", "capacity_mode", "default_capacity", "max_players", "slot_interval_min", "buffer_min", "is_active"] as const)
          .filter((k) => r[k] !== resource[k])
          .map((k) => [k, r[k]]),
      );
      return api<Resource>(`/admin/resources/${resource.id}`, { method: "PATCH", body });
    },
    onSuccess: () => {
      onSaved();
      onClose();
    },
  });
  const n = (k: keyof Resource) => (e: React.ChangeEvent<HTMLInputElement>) => setR({ ...r, [k]: Number(e.target.value) });
  return (
    <Modal open onClose={onClose} title={`Edit ${resource.name}`}>
      <div className="space-y-3 text-sm">
        <div>
          <label className="label" htmlFor="rs-name">Name</label>
          <input id="rs-name" className="input" value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="rs-max">Max players per group</label>
            <input id="rs-max" type="number" min={1} className="input" value={r.max_players} onChange={n("max_players")} />
          </div>
          <div>
            <label className="label" htmlFor="rs-interval">Start a game every (min)</label>
            <input id="rs-interval" type="number" min={5} max={240} className="input" value={r.slot_interval_min} onChange={n("slot_interval_min")} />
          </div>
          <div>
            <label className="label" htmlFor="rs-buffer">Gap between groups (min)</label>
            <input id="rs-buffer" type="number" min={0} max={120} className="input" value={r.buffer_min} onChange={n("buffer_min")} />
          </div>
          {r.capacity_mode === "SHARED_SEATS" && (
            <div>
              <label className="label" htmlFor="rs-cap">Places per slot</label>
              <input id="rs-cap" type="number" min={1} className="input" value={r.default_capacity} onChange={n("default_capacity")} />
            </div>
          )}
        </div>
        <p className="text-xs text-slate-500">
          Changing how often games start is only possible when there are no future bookings for this arena.
        </p>
        <ErrorBox error={m.error} />
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={m.isPending} onClick={() => m.mutate()}>Save</button>
      </div>
    </Modal>
  );
}

function BookingRulesSection({ editable }: { editable: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings", "booking"], queryFn: () => api<BookingSettings>("/admin/settings/booking") });
  const [d, setD] = useState<BookingSettings | null>(null);
  useEffect(() => {
    if (q.data) setD(q.data);
  }, [q.data]);
  const m = useMutation({
    mutationFn: () => api<BookingSettings>("/admin/settings/booking", { method: "PUT", body: d }),
    onSuccess: (data) => qc.setQueryData(["settings", "booking"], data),
  });
  if (q.isPending || !d) return <div className="card"><Loading /></div>;
  if (q.isError) return <ErrorBox error={q.error} />;
  const field = (k: keyof BookingSettings, label: string, help: string, min: number, max: number) => (
    <div>
      <label className="label" htmlFor={`bs-${k}`}>{label}</label>
      <input id={`bs-${k}`} type="number" min={min} max={max} className="input" value={d[k]} onChange={(e) => setD({ ...d, [k]: Number(e.target.value) })} />
      <p className="mt-1 text-xs text-slate-500">{help}</p>
    </div>
  );
  return (
    <section className="card p-4">
      <h2 className="font-semibold">Booking rules</h2>
      <p className="mb-4 text-sm text-slate-500">{editable ? "Owner only." : "Only the owner can change these."}</p>
      <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {field("max_days_ahead", "Book up to (days ahead)", "How far in advance customers can book", 0, 365)}
        {field("same_day_cutoff_min", "Same-day cutoff (min)", "Stop selling a slot this long before it starts", 0, 720)}
        {field("large_group_threshold", "Large group from (players)", "Bigger groups are sent to an event enquiry", 1, 1000)}
        {field("hold_ttl_seconds", "Slot hold (seconds)", "How long a slot is reserved while the customer finishes", 60, 1800)}
      </fieldset>
      {editable && (
        <div className="mt-4 flex items-center justify-end gap-3">
          <ErrorBox error={m.error} />
          {m.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
          <button className="btn-primary" disabled={m.isPending || JSON.stringify(d) === JSON.stringify(q.data)} onClick={() => m.mutate()}>
            Save rules
          </button>
        </div>
      )}
    </section>
  );
}

function BusinessInfoSection({ editable }: { editable: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["business-info"], queryFn: () => api<BusinessInfo>("/admin/business-info") });
  const [d, setD] = useState<BusinessInfo | null>(null);
  useEffect(() => {
    if (q.data) setD(q.data);
  }, [q.data]);
  const m = useMutation({
    mutationFn: () => {
      const body = Object.fromEntries(
        (["name", "address", "city", "postal_code", "phone", "whatsapp", "email", "maps_url"] as const)
          .filter((k) => d![k] !== q.data![k])
          .map((k) => [k, d![k]]),
      );
      return api<BusinessInfo>("/admin/business-info", { method: "PATCH", body });
    },
    onSuccess: (data) => qc.setQueryData(["business-info"], data),
  });
  if (q.isPending || !d) return <div className="card"><Loading /></div>;
  if (q.isError) return <ErrorBox error={q.error} />;
  const f = (k: keyof BusinessInfo, label: string, type = "text") => (
    <div>
      <label className="label" htmlFor={`bi-${k}`}>{label}</label>
      <input id={`bi-${k}`} type={type} className="input" value={d[k]} onChange={(e) => setD({ ...d, [k]: e.target.value })} />
    </div>
  );
  return (
    <section className="card p-4">
      <h2 className="font-semibold">Venue details</h2>
      <p className="mb-4 text-sm text-slate-500">Used by the voice assistant and in WhatsApp messages.</p>
      <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-2">
        {f("name", "Venue name")}
        {f("address", "Address")}
        {f("city", "City")}
        {f("postal_code", "PIN code")}
        {f("phone", "Phone", "tel")}
        {f("whatsapp", "WhatsApp", "tel")}
        {f("email", "Email", "email")}
        {f("maps_url", "Google Maps link", "url")}
      </fieldset>
      {editable && (
        <div className="mt-4 flex items-center justify-end gap-3">
          <ErrorBox error={m.error} />
          {m.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
          <button className="btn-primary" disabled={m.isPending || JSON.stringify(d) === JSON.stringify(q.data)} onClick={() => m.mutate()}>
            Save details
          </button>
        </div>
      )}
    </section>
  );
}
