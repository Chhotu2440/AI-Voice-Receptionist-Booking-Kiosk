import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Badge, Drawer, Empty, ErrorBox, Loading, PageHeader } from "../components/ui";
import { api, qs } from "../lib/api";
import { dateLabel, dateTime, titleCase } from "../lib/format";
import type { Enquiry, Page } from "../lib/types";

const COLUMNS = ["NEW", "CONTACTED", "QUOTED", "WON", "LOST"] as const;

/** Event enquiries as a pipeline board (doc 14 §4). Large groups and special events land here. */
export function EnquiriesPage() {
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["enquiries", q],
    queryFn: () => api<Page<Enquiry>>(`/admin/enquiries${qs({ q: q.trim(), page_size: 100 })}`),
    placeholderData: (prev) => prev,
  });
  const open = list.data?.items.find((e) => e.id === openId) ?? null;

  return (
    <>
      <PageHeader
        title="Event enquiries"
        subtitle="Large groups, birthdays and corporate events that need a quote. Call new enquiries promptly."
        actions={
          <input className="input w-64" placeholder="Search name, phone or reference" value={q} onChange={(e) => setQ(e.target.value)} />
        }
      />
      {list.isPending ? (
        <Loading />
      ) : list.isError ? (
        <ErrorBox error={list.error} />
      ) : list.data.items.length === 0 ? (
        <div className="card"><Empty>No enquiries yet.</Empty></div>
      ) : (
        <div className="grid gap-4 overflow-x-auto md:grid-cols-3 xl:grid-cols-5">
          {COLUMNS.map((col) => {
            const items = list.data.items.filter((e) => e.status === col);
            return (
              <section key={col} className="min-w-[220px] rounded-xl bg-slate-100 p-3 dark:bg-slate-900/60" data-testid={`col-${col}`}>
                <h2 className="mb-3 flex items-center justify-between text-sm font-semibold">
                  {titleCase(col)}
                  <span className="rounded-full bg-white px-2 text-xs text-slate-500 dark:bg-slate-800">{items.length}</span>
                </h2>
                <div className="space-y-2">
                  {items.map((e) => (
                    <button
                      key={e.id}
                      onClick={() => setOpenId(e.id)}
                      className="card block w-full p-3 text-left transition hover:border-brand-400"
                    >
                      <div className="font-medium">{e.customer_name}</div>
                      <div className="mt-0.5 text-xs text-slate-500">
                        {titleCase(e.occasion_code)} · {e.guest_count} people
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        {e.preferred_date ? `Wants ${dateLabel(e.preferred_date)}` : "No date yet"} · {dateTime(e.created_at)}
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
      <EnquiryDrawer enquiry={open} onClose={() => setOpenId(null)} />
    </>
  );
}

function EnquiryDrawer({ enquiry, onClose }: { enquiry: Enquiry | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");
  useEffect(() => {
    setStatus(enquiry?.status ?? "");
    setNotes(enquiry?.staff_notes ?? "");
  }, [enquiry?.id, enquiry?.status, enquiry?.staff_notes]);

  const m = useMutation({
    mutationFn: () => api<Enquiry>(`/admin/enquiries/${enquiry!.id}`, { method: "PATCH", body: { status, staff_notes: notes } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["enquiries"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  return (
    <Drawer open={!!enquiry} onClose={onClose} title={enquiry ? `Enquiry ${enquiry.reference}` : ""}>
      {enquiry && (
        <div className="space-y-5 text-sm">
          <div className="flex items-center gap-2">
            <Badge status={enquiry.status} />
            <span className="text-slate-500">via {titleCase(enquiry.channel)} · {dateTime(enquiry.created_at)}</span>
          </div>
          <dl className="grid grid-cols-2 gap-4">
            <div><dt className="label">Name</dt><dd>{enquiry.customer_name}</dd></div>
            <div><dt className="label">Phone</dt><dd><a className="hover:underline" href={`tel:${enquiry.customer_phone}`}>{enquiry.customer_phone}</a></dd></div>
            <div><dt className="label">Occasion</dt><dd>{titleCase(enquiry.occasion_code)}</dd></div>
            <div><dt className="label">Group size</dt><dd>{enquiry.guest_count}</dd></div>
            <div><dt className="label">Preferred date</dt><dd>{enquiry.preferred_date ? dateLabel(enquiry.preferred_date) : "—"}</dd></div>
            {Object.entries(enquiry.details).map(([k, v]) => (
              <div key={k}><dt className="label">{titleCase(k)}</dt><dd>{String(v)}</dd></div>
            ))}
          </dl>
          <div>
            <label className="label" htmlFor="enq-status">Stage</label>
            <select id="enq-status" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              {COLUMNS.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="enq-notes">Staff notes</label>
            <textarea id="enq-notes" className="input min-h-[140px]" maxLength={4000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Called on…, quoted ₹…, follow up on…" />
          </div>
          <ErrorBox error={m.error} />
          {m.isSuccess && !m.isPending && <p className="text-sm text-emerald-600">Saved.</p>}
          <div className="flex justify-end">
            <button className="btn-primary" disabled={m.isPending} onClick={() => m.mutate()}>Save</button>
          </div>
        </div>
      )}
    </Drawer>
  );
}
