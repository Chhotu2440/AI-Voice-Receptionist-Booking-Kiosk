import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Badge, Drawer, Empty, ErrorBox, Loading, Modal, PageHeader, Pager } from "../components/ui";
import { api, qs } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateLabel, dateTime, money, titleCase } from "../lib/format";
import type { CustomerDetail, CustomerSummary, Page } from "../lib/types";

const PAGE_SIZE = 25;
const PURPOSE_LABEL: Record<string, string> = { WHATSAPP_TRANSACTIONAL: "WhatsApp booking messages" };

export function CustomersPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const openId = params.get("id");
  const query = qs({ q: q.trim(), page, page_size: PAGE_SIZE });
  const list = useQuery({
    queryKey: ["customers", query],
    queryFn: () => api<Page<CustomerSummary>>(`/admin/customers${query}`),
    placeholderData: (prev) => prev,
  });
  const open = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("id", id);
    else next.delete("id");
    setParams(next, { replace: !id });
  };

  return (
    <>
      <PageHeader title="Customers" subtitle="Look up a customer by name or phone; see their bookings and consents." />
      <div className="card mb-4 p-4">
        <label className="label" htmlFor="cust-q">Name or phone</label>
        <input
          id="cust-q"
          className="input max-w-md"
          placeholder="e.g. Riya or 98765 43210 or last 4 digits"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
      </div>
      <div className="card overflow-hidden">
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <div className="p-4"><ErrorBox error={list.error} /></div>
        ) : list.data.items.length === 0 ? (
          <Empty>No customers match.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/60">
                <tr>
                  <th className="th">Customer</th>
                  <th className="th">Bookings</th>
                  <th className="th">Spent</th>
                  <th className="th">Last booking</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {list.data.items.map((c) => (
                  <tr key={c.id} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50" onClick={() => open(c.id)}>
                    <td className="td">
                      <div className="font-medium">
                        {c.name} {c.anonymized_at && <Badge status="DISABLED" label="Anonymized" />}
                      </div>
                      <div className="text-xs text-slate-500">{c.phone || c.phone_masked}</div>
                    </td>
                    <td className="td tabular-nums">{c.bookings}</td>
                    <td className="td tabular-nums">{money(c.total_spent)}</td>
                    <td className="td text-sm">{dateTime(c.last_booking_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && list.data.total > 0 && <Pager page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={setPage} />}
      </div>
      <CustomerDrawer id={openId} onClose={() => open(null)} />
    </>
  );
}

function CustomerDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const c = useQuery({ queryKey: ["customer", id], queryFn: () => api<CustomerDetail>(`/admin/customers/${id}`), enabled: !!id });
  const [editing, setEditing] = useState(false);
  const [erasing, setErasing] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);
  const updated = (d: CustomerDetail) => {
    qc.setQueryData(["customer", id], d);
    void qc.invalidateQueries({ queryKey: ["customers"] });
    setEditing(false);
    setErasing(false);
  };

  async function download() {
    setExportError(null);
    try {
      const data = await api<unknown>(`/admin/customers/${id}/export`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `customer-${id}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setExportError(e);
    }
  }

  const d = c.data;
  return (
    <Drawer open={!!id} onClose={onClose} title={d?.name ?? "Customer"} wide>
      {c.isPending ? (
        <Loading />
      ) : c.isError ? (
        <ErrorBox error={c.error} />
      ) : d ? (
        <div className="space-y-6 text-sm" data-testid="customer-detail">
          {d.anonymized_at && (
            <div className="rounded-lg bg-slate-100 px-3 py-2 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              Personal data was erased on {dateTime(d.anonymized_at)}. Booking and payment records are kept without identity.
            </div>
          )}
          <dl className="grid grid-cols-2 gap-4">
            <div><dt className="label">Phone</dt><dd>{d.phone ? <a className="hover:underline" href={`tel:${d.phone}`}>{d.phone}</a> : "—"}</dd></div>
            <div><dt className="label">Email</dt><dd>{d.email ?? "—"}</dd></div>
            <div><dt className="label">Language</dt><dd>{d.preferred_language === "hi" ? "Hindi" : "English"}</dd></div>
            <div><dt className="label">First seen</dt><dd>{dateTime(d.first_seen_at)}</dd></div>
            <div><dt className="label">Bookings</dt><dd>{d.bookings} · {money(d.total_spent)}</dd></div>
            <div>
              <dt className="label">Consents</dt>
              <dd>
                {Object.keys(d.consents).length === 0
                  ? "None recorded"
                  : Object.entries(d.consents).map(([p, g]) => (
                      <div key={p}>{PURPOSE_LABEL[p] ?? titleCase(p)}: <strong>{g ? "Yes" : "No"}</strong></div>
                    ))}
              </dd>
            </div>
          </dl>

          {!d.anonymized_at && can("customer.write") && (
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={() => setEditing(true)}>Correct details</button>
              <button className="btn-secondary" onClick={() => void download()} data-testid="export-customer">Export data (JSON)</button>
              <button className="btn-danger" onClick={() => setErasing(true)} data-testid="anonymize-customer">Erase personal data…</button>
            </div>
          )}
          <ErrorBox error={exportError} />

          <section>
            <h3 className="mb-2 font-semibold">Bookings</h3>
            {d.bookings_list.length === 0 ? (
              <p className="text-slate-500">None.</p>
            ) : (
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
                {d.bookings_list.map((b) => (
                  <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <div>
                      <Link className="font-medium hover:underline" to={`/bookings?ref=${b.reference}`}>{b.reference}</Link>
                      <span className="text-slate-500"> · {dateLabel(b.date)} {b.start_time} · {b.package_name} · {b.guest_count} players</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="tabular-nums">{money(b.total)}</span>
                      <Badge status={b.status} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {d.enquiries.length > 0 && (
            <section>
              <h3 className="mb-2 font-semibold">Event enquiries</h3>
              <ul className="space-y-1">
                {d.enquiries.map((e) => (
                  <li key={e.id} className="flex items-center gap-2">
                    <Badge status={e.status} /> {e.reference} · {e.guest_count} people · {dateTime(e.created_at)}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="mb-2 font-semibold">Consent history</h3>
            {d.consent_log.length === 0 ? (
              <p className="text-slate-500">None.</p>
            ) : (
              <ul className="space-y-1 text-slate-600 dark:text-slate-300">
                {d.consent_log.map((l, i) => (
                  <li key={i}>
                    {dateTime(l.created_at)} · {PURPOSE_LABEL[l.purpose] ?? titleCase(l.purpose)}:{" "}
                    <strong>{l.granted ? "granted" : "withdrawn"}</strong> via {titleCase(l.channel)} (notice {l.notice_version})
                  </li>
                ))}
              </ul>
            )}
          </section>

          {editing && <CorrectModal customer={d} onClose={() => setEditing(false)} onDone={updated} />}
          {erasing && <AnonymizeModal customer={d} onClose={() => setErasing(false)} onDone={updated} />}
        </div>
      ) : null}
    </Drawer>
  );
}

function CorrectModal({ customer, onClose, onDone }: { customer: CustomerDetail; onClose: () => void; onDone: (d: CustomerDetail) => void }) {
  const [name, setName] = useState(customer.name);
  const [email, setEmail] = useState(customer.email ?? "");
  const [lang, setLang] = useState(customer.preferred_language);
  useEffect(() => setName(customer.name), [customer.name]);
  const m = useMutation({
    mutationFn: () =>
      api<CustomerDetail>(`/admin/customers/${customer.id}`, {
        method: "PATCH",
        body: { name: name.trim(), email: email.trim(), preferred_language: lang },
      }),
    onSuccess: onDone,
  });
  return (
    <Modal open onClose={onClose} title="Correct customer details">
      <p className="mb-3 text-sm text-slate-500">The phone number identifies the customer and can't be changed here.</p>
      <div className="space-y-3">
        <div>
          <label className="label" htmlFor="c-name">Name</label>
          <input id="c-name" autoFocus className="input" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="c-email">Email (optional)</label>
          <input id="c-email" type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="c-lang">Language</label>
          <select id="c-lang" className="input" value={lang} onChange={(e) => setLang(e.target.value)}>
            <option value="en">English</option>
            <option value="hi">Hindi</option>
          </select>
        </div>
        <ErrorBox error={m.error} />
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={m.isPending || !name.trim()} onClick={() => m.mutate()}>Save</button>
      </div>
    </Modal>
  );
}

function AnonymizeModal({ customer, onClose, onDone }: { customer: CustomerDetail; onClose: () => void; onDone: (d: CustomerDetail) => void }) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const m = useMutation({
    mutationFn: () =>
      api<CustomerDetail>(`/admin/customers/${customer.id}/anonymize`, {
        method: "POST",
        body: { reason: reason.trim(), confirm: typed },
      }),
    onSuccess: onDone,
  });
  return (
    <Modal open onClose={onClose} title={`Erase ${customer.name}'s personal data?`}>
      <div className="space-y-3 text-sm">
        <p className="text-slate-600 dark:text-slate-300">
          Removes name, phone, email, booking notes and message contents. Bookings and amounts stay for accounts, without
          identity. <strong>This can't be undone.</strong> Upcoming bookings must be cancelled first.
        </p>
        <div>
          <label className="label" htmlFor="an-reason">Reason</label>
          <input id="an-reason" autoFocus className="input" placeholder="e.g. Customer asked to delete their data" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="an-confirm">Type ANONYMIZE to confirm</label>
          <input id="an-confirm" className="input font-mono" value={typed} onChange={(e) => setTyped(e.target.value)} />
        </div>
        <ErrorBox error={m.error} />
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button
          className="btn-danger"
          disabled={m.isPending || reason.trim().length < 3 || typed !== "ANONYMIZE"}
          onClick={() => m.mutate()}
          data-testid="confirm-anonymize"
        >
          Erase data
        </button>
      </div>
    </Modal>
  );
}
