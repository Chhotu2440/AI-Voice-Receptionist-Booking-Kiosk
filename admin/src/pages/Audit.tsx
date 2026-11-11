import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";

import { Empty, ErrorBox, Loading, PageHeader, Pager } from "../components/ui";
import { api, qs } from "../lib/api";
import { dateTime, titleCase } from "../lib/format";
import type { AuditEntry, Page } from "../lib/types";

const PAGE_SIZE = 50;
const ENTITIES = [
  "booking",
  "customer",
  "enquiry",
  "user",
  "kiosk",
  "package",
  "occasion",
  "pricing_rule",
  "business_hours",
  "schedule_exception",
  "resource",
  "business_location",
  "system_settings",
];

/** Read-only trail of who changed what (append-only on the server). */
export function AuditPage() {
  const [entity, setEntity] = useState("");
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);
  const query = qs({ entity_type: entity, action: action.trim(), from, to, page, page_size: PAGE_SIZE });
  const list = useQuery({
    queryKey: ["audit", query],
    queryFn: () => api<Page<AuditEntry>>(`/admin/audit${query}`),
    placeholderData: (prev) => prev,
  });
  const reset = () => setPage(1);

  return (
    <>
      <PageHeader title="Audit log" subtitle="Every change made by staff, kiosks, the AI and the system. Entries can't be edited or deleted." />
      <div className="card mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="label" htmlFor="a-entity">Record type</label>
          <select id="a-entity" className="input" value={entity} onChange={(e) => { setEntity(e.target.value); reset(); }}>
            <option value="">All</option>
            {ENTITIES.map((x) => <option key={x} value={x}>{titleCase(x)}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="a-action">Action starts with</label>
          <input id="a-action" className="input" placeholder="e.g. booking.cancel" value={action} onChange={(e) => { setAction(e.target.value); reset(); }} />
        </div>
        <div>
          <label className="label" htmlFor="a-from">From</label>
          <input id="a-from" type="date" className="input" value={from} onChange={(e) => { setFrom(e.target.value); reset(); }} />
        </div>
        <div>
          <label className="label" htmlFor="a-to">To</label>
          <input id="a-to" type="date" className="input" value={to} onChange={(e) => { setTo(e.target.value); reset(); }} />
        </div>
      </div>
      <div className="card overflow-hidden">
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <div className="p-4"><ErrorBox error={list.error} /></div>
        ) : list.data.items.length === 0 ? (
          <Empty>Nothing recorded for these filters.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/60">
                <tr>
                  <th className="th">When</th>
                  <th className="th">Who</th>
                  <th className="th">Action</th>
                  <th className="th">Record</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {list.data.items.map((a) => (
                  <Fragment key={a.id}>
                    <tr>
                      <td className="td whitespace-nowrap text-sm">{dateTime(a.created_at)}</td>
                      <td className="td text-sm">
                        {a.actor_name ?? titleCase(a.actor_type)}
                        {a.ip && <div className="text-xs text-slate-500">{a.ip}</div>}
                      </td>
                      <td className="td font-mono text-xs">{a.action}</td>
                      <td className="td text-sm">
                        {titleCase(a.entity_type)}
                        {a.entity_id && <div className="max-w-[16rem] truncate font-mono text-xs text-slate-500">{a.entity_id}</div>}
                      </td>
                      <td className="td text-right">
                        {(a.before || a.after) && (
                          <button className="btn-secondary !py-1 text-xs" onClick={() => setExpanded(expanded === a.id ? null : a.id)}>
                            {expanded === a.id ? "Hide" : "Changes"}
                          </button>
                        )}
                      </td>
                    </tr>
                    {expanded === a.id && (
                      <tr>
                        <td colSpan={5} className="bg-slate-50 px-4 py-3 dark:bg-slate-900/60">
                          <div className="grid gap-3 md:grid-cols-2">
                            <Json label="Before" value={a.before} />
                            <Json label="After" value={a.after} />
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && list.data.total > 0 && <Pager page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={setPage} />}
      </div>
    </>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <div className="label">{label}</div>
      <pre className="max-h-64 overflow-auto rounded-lg bg-white p-2 text-xs dark:bg-slate-950">{value ? JSON.stringify(value, null, 2) : "—"}</pre>
    </div>
  );
}
