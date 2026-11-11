import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { SlotPicker } from "../components/SlotPicker";
import { Badge, Drawer, Empty, ErrorBox, Loading, Modal, PageHeader, Pager } from "../components/ui";
import { api, idempotencyKey, qs } from "../lib/api";
import { useAuth } from "../lib/auth";
import { addDays, dateLabel, dateTime, money, titleCase, todayIST } from "../lib/format";
import type { Booking, Hold, Notification, Occasion, Page, PackageT } from "../lib/types";

const STATUSES = ["CONFIRMED", "COMPLETED", "NO_SHOW", "CANCELLED"];
const PAGE_SIZE = 25;

export function BookingsPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const today = todayIST();
  const ref = params.get("ref") ?? "";
  const [from, setFrom] = useState(ref ? "" : today);
  const [to, setTo] = useState(ref ? "" : addDays(today, 30));
  const [status, setStatus] = useState<string>("");
  const [search, setSearch] = useState(ref);
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const term = search.trim();
  const isPhone = /^[+\d\s-]{10,}$/.test(term);
  const query = qs({
    from: term ? undefined : from,
    to: term ? undefined : to,
    status: status ? [status] : undefined,
    reference: term && !isPhone ? term : undefined,
    phone: term && isPhone ? term : undefined,
    page,
    page_size: PAGE_SIZE,
  });
  const list = useQuery({
    queryKey: ["bookings", query],
    queryFn: () => api<Page<Booking>>(`/admin/bookings${query}`),
    placeholderData: (prev) => prev,
  });

  // Opening a booking from the dashboard (?ref=...) jumps straight to it.
  const first = list.data?.items[0];
  useEffect(() => {
    if (ref && first && first.reference === ref.toUpperCase()) {
      setOpenId(first.id);
      const next = new URLSearchParams(params);
      next.delete("ref");
      setParams(next, { replace: true });
    }
  }, [ref, first, params, setParams]);

  return (
    <>
      <PageHeader
        title="Bookings"
        subtitle="Search by reference or phone, or browse by date."
        actions={
          can("booking.write") && (
            <button className="btn-primary" onClick={() => setCreating(true)} data-testid="new-booking">
              + New booking
            </button>
          )
        }
      />
      <div className="card mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <label className="label" htmlFor="search">Reference or phone</label>
          <input
            id="search"
            className="input"
            placeholder="PLT-XXXX or 98765 43210"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div>
          <label className="label" htmlFor="from">From</label>
          <input id="from" type="date" className="input" value={from} disabled={!!term} onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
        </div>
        <div>
          <label className="label" htmlFor="to">To</label>
          <input id="to" type="date" className="input" value={to} disabled={!!term} onChange={(e) => { setTo(e.target.value); setPage(1); }} />
        </div>
        <div>
          <label className="label" htmlFor="status">Status</label>
          <select id="status" className="input" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{titleCase(s)}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="card overflow-hidden">
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <div className="p-4"><ErrorBox error={list.error} /></div>
        ) : list.data.items.length === 0 ? (
          <Empty>No bookings match.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/60">
                <tr>
                  <th className="th">When</th>
                  <th className="th">Customer</th>
                  <th className="th">Package</th>
                  <th className="th">Players</th>
                  <th className="th">Total</th>
                  <th className="th">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {list.data.items.map((b) => (
                  <tr
                    key={b.id}
                    className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50"
                    onClick={() => setOpenId(b.id)}
                    data-testid={`booking-row-${b.reference}`}
                  >
                    <td className="td whitespace-nowrap">
                      <div className="font-medium">{dateLabel(b.date)}</div>
                      <div className="text-xs tabular-nums text-slate-500">{b.start_time}–{b.end_time}</div>
                    </td>
                    <td className="td">
                      <div className="font-medium">{b.customer.name}</div>
                      <div className="text-xs text-slate-500">{b.reference} · {b.customer_phone}</div>
                    </td>
                    <td className="td">{b.package_name}</td>
                    <td className="td tabular-nums">{b.guest_count}</td>
                    <td className="td tabular-nums">{money(b.pricing.total)}</td>
                    <td className="td"><Badge status={b.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && list.data.total > 0 && (
          <Pager page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={setPage} />
        )}
      </div>

      <BookingDrawer id={openId} onClose={() => setOpenId(null)} />
      <NewBookingDrawer open={creating} onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); setOpenId(id); }} />
    </>
  );
}

function BookingDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [action, setAction] = useState<null | "cancel" | "reschedule" | "COMPLETED" | "NO_SHOW">(null);
  const b = useQuery({ queryKey: ["booking", id], queryFn: () => api<Booking>(`/admin/bookings/${id}`), enabled: !!id });
  const notes = useQuery({
    queryKey: ["notifications", id],
    queryFn: () => api<Page<Notification>>(`/admin/notifications${qs({ booking_id: id })}`),
    enabled: !!id,
  });
  const refreshAll = (updated: Booking) => {
    qc.setQueryData(["booking", id], updated);
    void qc.invalidateQueries({ queryKey: ["bookings"] });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
    setAction(null);
  };

  const data = b.data;
  const isLive = data?.status === "CONFIRMED";
  const started = data ? new Date(data.start_at).getTime() <= Date.now() : false;

  return (
    <Drawer open={!!id} onClose={onClose} title={data ? `Booking ${data.reference}` : "Booking"} wide>
      {b.isPending ? (
        <Loading />
      ) : b.isError ? (
        <ErrorBox error={b.error} />
      ) : data ? (
        <div className="space-y-6" data-testid="booking-detail">
          <div className="flex flex-wrap items-center gap-2">
            <Badge status={data.status} />
            <Badge status={data.payment_status} label={`Payment: ${titleCase(data.payment_status)}`} />
            <span className="text-sm text-slate-500">via {titleCase(data.channel)}</span>
          </div>

          <dl className="grid grid-cols-2 gap-4 text-sm">
            <Field label="Customer" value={data.customer.name} />
            <Field label="Phone" value={<a className="hover:underline" href={`tel:${data.customer_phone}`}>{data.customer_phone}</a>} />
            <Field label="When" value={`${dateLabel(data.date)}, ${data.start_time}–${data.end_time}`} />
            <Field label="Package" value={`${data.package_name} · ${data.guest_count} players`} />
            <Field label="Occasion" value={titleCase(data.occasion_code)} />
            <Field label="Payment" value={titleCase(data.payment_mode)} />
            {Object.keys(data.occasion_details).length > 0 && (
              <Field
                label="Occasion details"
                value={Object.entries(data.occasion_details).map(([k, v]) => `${titleCase(k)}: ${String(v)}`).join(" · ")}
              />
            )}
            {data.notes && <Field label="Notes" value={data.notes} />}
            {data.cancel_reason && <Field label="Cancel reason" value={data.cancel_reason} />}
          </dl>

          <section>
            <h3 className="mb-2 text-sm font-semibold">Price (as quoted at booking)</h3>
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                <Row label={`${data.guest_count} × ${money(data.pricing.price_per_person)} (${titleCase(data.pricing.day_type)})`} value={money(data.pricing.subtotal)} />
                {data.pricing.discounts.map((d) => (
                  <Row key={d.rule_id} label={`${d.name} (−${Number(d.pct)}%)`} value={`−${money(d.amount)}`} />
                ))}
                {data.pricing.charges.map((c) => (
                  <Row key={c.code} label={c.label} value={money(c.amount)} />
                ))}
                <Row
                  label={`GST ${Number(data.pricing.tax.rate)}% ${data.pricing.tax.included ? "(included)" : ""}`}
                  value={money(data.pricing.tax.amount)}
                />
                <Row label={<strong>Total</strong>} value={<strong>{money(data.pricing.total)}</strong>} />
              </tbody>
            </table>
          </section>

          {can("booking.write") && isLive && (
            <section className="flex flex-wrap gap-2">
              {!started && (
                <button className="btn-secondary" onClick={() => setAction("reschedule")} data-testid="reschedule">
                  Reschedule
                </button>
              )}
              {started && (
                <>
                  <button className="btn-secondary" onClick={() => setAction("COMPLETED")} data-testid="mark-completed">
                    Mark completed
                  </button>
                  <button className="btn-secondary" onClick={() => setAction("NO_SHOW")}>
                    Mark no-show
                  </button>
                </>
              )}
              <button className="btn-danger" onClick={() => setAction("cancel")} data-testid="cancel-booking">
                Cancel booking
              </button>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-sm font-semibold">WhatsApp</h3>
            {notes.data?.items.length ? (
              <ul className="space-y-1 text-sm">
                {notes.data.items.map((n) => (
                  <li key={n.id} className="flex flex-wrap items-center gap-2">
                    <Badge status={n.status} />
                    <span>{n.template}</span>
                    <span className="text-slate-500">to {n.to_masked} · {dateTime(n.created_at)}</span>
                    {n.error && <span className="text-rose-600">{n.error}</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">No messages (customer did not opt in, or none sent yet).</p>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">History</h3>
            <ol className="space-y-2 border-l border-slate-200 pl-4 text-sm dark:border-slate-700">
              {data.history.map((h, i) => (
                <li key={i}>
                  <span className="font-medium">
                    {h.from_status === h.to_status
                      ? "Changed"
                      : `${h.from_status ? `${titleCase(h.from_status)} → ` : ""}${titleCase(h.to_status)}`}
                  </span>
                  <span className="text-slate-500"> · {dateTime(h.created_at)} · {titleCase(h.actor_type)}</span>
                  {h.reason && <div className="text-slate-500">{h.reason}</div>}
                </li>
              ))}
            </ol>
          </section>

          <CancelModal booking={data} open={action === "cancel"} onClose={() => setAction(null)} onDone={refreshAll} />
          <StatusModal booking={data} status={action === "COMPLETED" || action === "NO_SHOW" ? action : null} onClose={() => setAction(null)} onDone={refreshAll} />
          {action === "reschedule" && <RescheduleModal booking={data} onClose={() => setAction(null)} onDone={refreshAll} />}
        </div>
      ) : null}
    </Drawer>
  );
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Row({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <tr>
      <td className="py-1.5">{label}</td>
      <td className="py-1.5 text-right tabular-nums">{value}</td>
    </tr>
  );
}

function CancelModal({ booking, open, onClose, onDone }: { booking: Booking; open: boolean; onClose: () => void; onDone: (b: Booking) => void }) {
  const [reason, setReason] = useState("");
  const m = useMutation({
    mutationFn: () => api<Booking>(`/admin/bookings/${booking.id}/cancel`, { method: "POST", body: { reason } }),
    onSuccess: onDone,
  });
  return (
    <Modal open={open} onClose={onClose} title={`Cancel ${booking.reference}?`}>
      <p className="mb-3 text-sm text-slate-500">The slot is released immediately. This can't be undone.</p>
      <label className="label" htmlFor="cancel-reason">Reason</label>
      <input id="cancel-reason" autoFocus className="input mb-3" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Customer called to cancel" />
      <ErrorBox error={m.error} />
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Keep booking</button>
        <button className="btn-danger" disabled={reason.trim().length < 3 || m.isPending} onClick={() => m.mutate()} data-testid="confirm-cancel">
          Cancel booking
        </button>
      </div>
    </Modal>
  );
}

function StatusModal({ booking, status, onClose, onDone }: { booking: Booking; status: "COMPLETED" | "NO_SHOW" | null; onClose: () => void; onDone: (b: Booking) => void }) {
  const m = useMutation({
    mutationFn: () => api<Booking>(`/admin/bookings/${booking.id}/status`, { method: "POST", body: { status } }),
    onSuccess: onDone,
  });
  return (
    <Modal open={status !== null} onClose={onClose} title={status === "NO_SHOW" ? "Mark as no-show?" : "Mark as completed?"}>
      <p className="mb-3 text-sm text-slate-500">{booking.customer.name} · {dateLabel(booking.date)} {booking.start_time}</p>
      <ErrorBox error={m.error} />
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Back</button>
        <button className="btn-primary" disabled={m.isPending} onClick={() => m.mutate()} data-testid="confirm-status">
          Confirm
        </button>
      </div>
    </Modal>
  );
}

function RescheduleModal({ booking, onClose, onDone }: { booking: Booking; onClose: () => void; onDone: (b: Booking) => void }) {
  const [date, setDate] = useState(booking.date);
  const [slot, setSlot] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const m = useMutation({
    mutationFn: async () => {
      const hold = await api<Hold>("/admin/slot-holds", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey() },
        body: { package_id: booking.package_id, date, start_time: slot, guest_count: booking.guest_count },
      });
      return api<Booking>(`/admin/bookings/${booking.id}/reschedule`, {
        method: "POST",
        body: { hold_id: hold.hold_id, hold_token: hold.hold_token, reason },
      });
    },
    onSuccess: onDone,
  });
  return (
    <Modal open onClose={onClose} title={`Reschedule ${booking.reference}`}>
      <p className="mb-3 text-sm text-slate-500">
        Now {dateLabel(booking.date)} {booking.start_time}. The price is recalculated for the new date.
      </p>
      <label className="label" htmlFor="rs-date">New date</label>
      <input id="rs-date" type="date" className="input mb-3" min={todayIST()} value={date} onChange={(e) => { setDate(e.target.value); setSlot(null); }} />
      <SlotPicker packageId={booking.package_id} date={date} guests={booking.guest_count} value={slot} onChange={setSlot} />
      <label className="label mt-3" htmlFor="rs-reason">Reason (optional)</label>
      <input id="rs-reason" className="input mb-3" value={reason} onChange={(e) => setReason(e.target.value)} />
      <ErrorBox error={m.error} />
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Back</button>
        <button className="btn-primary" disabled={!slot || m.isPending} onClick={() => m.mutate()} data-testid="confirm-reschedule">
          Move booking
        </button>
      </div>
    </Modal>
  );
}

function NewBookingDrawer({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: string) => void }) {
  const qc = useQueryClient();
  const packages = useQuery({ queryKey: ["packages-public"], queryFn: () => api<PackageT[]>("/packages"), enabled: open });
  const occasions = useQuery({ queryKey: ["occasions"], queryFn: () => api<Occasion[]>("/occasions"), enabled: open });
  const [packageId, setPackageId] = useState("");
  const [guests, setGuests] = useState(4);
  const [date, setDate] = useState(todayIST());
  const [slot, setSlot] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [occasion, setOccasion] = useState("FRIENDS_FAMILY");
  const [whatsapp, setWhatsapp] = useState(true);
  const [notes, setNotes] = useState("");

  const pkg = packages.data?.find((p) => p.id === packageId);
  const m = useMutation({
    mutationFn: async () => {
      const hold = await api<Hold>("/admin/slot-holds", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey() },
        body: { package_id: packageId, date, start_time: slot, guest_count: guests },
      });
      return api<Booking>("/admin/bookings", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey() },
        body: {
          hold_id: hold.hold_id,
          hold_token: hold.hold_token,
          customer: { name: name.trim(), phone: phone.trim() },
          occasion_code: occasion,
          consents: { whatsapp },
          notes,
        },
      });
    },
    onSuccess: (b) => {
      void qc.invalidateQueries({ queryKey: ["bookings"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      setSlot(null);
      setName("");
      setPhone("");
      setNotes("");
      onCreated(b.id);
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    m.mutate();
  }

  return (
    <Drawer open={open} onClose={onClose} title="New booking">
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="label" htmlFor="nb-package">Package</label>
            <select id="nb-package" className="input" required value={packageId} onChange={(e) => { setPackageId(e.target.value); setSlot(null); }}>
              <option value="">Choose…</option>
              {packages.data?.map((p) => (
                <option key={p.id} value={p.id}>{p.name_en} · {p.duration_min} min · {p.min_guests}–{p.max_guests} players</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="nb-guests">Players</label>
            <input id="nb-guests" type="number" className="input" min={pkg?.min_guests ?? 1} max={pkg?.max_guests ?? 50} required value={guests} onChange={(e) => { setGuests(Number(e.target.value)); setSlot(null); }} />
          </div>
          <div>
            <label className="label" htmlFor="nb-date">Date</label>
            <input id="nb-date" type="date" className="input" min={todayIST()} required value={date} onChange={(e) => { setDate(e.target.value); setSlot(null); }} />
          </div>
        </div>
        <div>
          <span className="label">Start time</span>
          <SlotPicker packageId={packageId} date={date} guests={guests} value={slot} onChange={setSlot} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="nb-name">Customer name</label>
            <input id="nb-name" className="input" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="nb-phone">Mobile</label>
            <input id="nb-phone" className="input" required inputMode="tel" placeholder="98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="label" htmlFor="nb-occasion">Occasion</label>
            <select id="nb-occasion" className="input" value={occasion} onChange={(e) => setOccasion(e.target.value)}>
              {occasions.data?.filter((o) => o.is_active && !o.always_enquiry).map((o) => (
                <option key={o.code} value={o.code}>{o.label_en}</option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <label className="label" htmlFor="nb-notes">Notes (optional)</label>
            <input id="nb-notes" className="input" maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={whatsapp} onChange={(e) => setWhatsapp(e.target.checked)} className="h-4 w-4 accent-brand-600" />
          Customer agrees to receive the confirmation on WhatsApp
        </label>
        <ErrorBox error={m.error} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
          <button className="btn-primary" disabled={!slot || m.isPending} data-testid="create-booking">
            {m.isPending ? "Booking…" : "Confirm booking"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
