import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Bars, Empty, ErrorBox, Loading, PageHeader, Stat } from "../components/ui";
import { api, qs } from "../lib/api";
import { addDays, dateLabel, money, titleCase, todayIST, usd } from "../lib/format";
import type { Dashboard } from "../lib/types";

const RANGES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
];

const FUNNEL_LABEL: Record<string, string> = {
  started: "Started",
  details: "Gave name & phone",
  package: "Saw packages",
  slot: "Picked a date",
  summary: "Reached summary",
  booked: "Booked",
};

export function DashboardPage() {
  const [days, setDays] = useState(30);
  const today = todayIST();
  const from = addDays(today, -(days - 1));
  const q = useQuery({
    queryKey: ["dashboard", from, today],
    queryFn: () => api<Dashboard>(`/admin/dashboard${qs({ from, to: today })}`),
    refetchInterval: 60_000,
  });

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={`Today is ${dateLabel(today)}. Revenue is what customers were quoted at booking.`}
        actions={RANGES.map((r) => (
          <button
            key={r.days}
            className={r.days === days ? "btn-primary" : "btn-secondary"}
            onClick={() => setDays(r.days)}
          >
            {r.label}
          </button>
        ))}
      />
      {q.isPending ? <Loading /> : q.isError ? <ErrorBox error={q.error} /> : <Body d={q.data} days={days} />}
    </>
  );
}

function Body({ d, days }: { d: Dashboard; days: number }) {
  const capPct = Number(d.ai.monthly_cap_usd) > 0 ? (Number(d.ai.month_usd) / Number(d.ai.monthly_cap_usd)) * 100 : 0;
  const started = d.funnel[0]?.sessions ?? 0;
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat testId="stat-today" label="Today's bookings" value={d.today.bookings} hint={`${d.today.guests} players · ${money(d.today.revenue)}`} />
        <Stat label="Next 7 days" value={d.upcoming_7_days} hint="confirmed bookings" />
        <Stat
          testId="stat-revenue"
          label={`Revenue · ${days} days`}
          value={money(d.totals.revenue)}
          hint={`${d.totals.bookings} bookings · avg ${money(d.totals.average_booking)} · ${d.totals.cancelled} cancelled`}
        />
        <Stat
          label="Open enquiries"
          value={<Link to="/enquiries" className="hover:underline">{d.open_enquiries}</Link>}
          hint="new or contacted"
          tone={d.open_enquiries > 0 ? "warn" : "default"}
        />
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h2 className="border-b border-slate-200 px-4 py-3 font-semibold dark:border-slate-800">Today's schedule</h2>
          {d.today.list.length === 0 ? (
            <Empty>No bookings today yet.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {d.today.list.map((b) => (
                    <tr key={b.id} className={b.upcoming ? "" : "opacity-60"}>
                      <td className="td font-medium tabular-nums">
                        {b.start_time}–{b.end_time}
                      </td>
                      <td className="td">
                        <Link to={`/bookings?ref=${b.reference}`} className="font-medium hover:underline">
                          {b.customer_name}
                        </Link>
                        <div className="text-xs text-slate-500">
                          {b.reference} · {titleCase(b.channel)}
                        </div>
                      </td>
                      <td className="td tabular-nums">{b.guest_count} players</td>
                      <td className="td tabular-nums">{money(b.total)}</td>
                      <td className="td">
                        <Badge status={b.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="card p-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">Kiosks</h2>
              <Link to="/kiosks" className="text-sm text-brand-600 hover:underline">Manage</Link>
            </div>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {d.kiosks.online}
              <span className="text-base font-normal text-slate-500"> / {d.kiosks.active} online</span>
            </p>
            {d.kiosks.active > d.kiosks.online && (
              <p className="mt-1 text-sm text-amber-600">A kiosk has not checked in for over 3 minutes.</p>
            )}
          </div>
          <div className={`card p-4 ${d.ai.voice_allowed ? "" : "ring-1 ring-rose-400"}`}>
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">Voice AI cost</h2>
              <Link to="/ai" className="text-sm text-brand-600 hover:underline">Details</Link>
            </div>
            <p className="mt-2 text-sm text-slate-500">
              Today {usd(d.ai.today_usd)} of {usd(d.ai.daily_cap_usd, 0)} · Month {usd(d.ai.month_usd)} (≈ ₹{d.ai.month_inr}) of{" "}
              {usd(d.ai.monthly_cap_usd, 0)}
            </p>
            <div className="mt-2 h-2 rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className={`h-2 rounded-full ${capPct >= 90 ? "bg-rose-500" : capPct >= 70 ? "bg-amber-500" : "bg-emerald-500"}`}
                style={{ width: `${Math.min(100, capPct)}%` }}
              />
            </div>
            {!d.ai.voice_allowed && (
              <p className="mt-2 text-sm font-medium text-rose-600">Budget reached: kiosks are on touch only.</p>
            )}
          </div>
        </div>
      </section>

      <section className="card p-4">
        <h2 className="mb-4 font-semibold">Bookings per day</h2>
        <DayChart rows={d.by_day} from={d.from} to={d.to} />
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="card p-4">
          <h2 className="mb-1 font-semibold">Kiosk funnel</h2>
          <p className="mb-4 text-xs text-slate-500">
            {d.kiosk_sessions.total} sessions · {d.kiosk_sessions.voice} used voice
          </p>
          <Bars
            rows={d.funnel.map((f) => ({
              label: FUNNEL_LABEL[f.step] ?? f.step,
              value: f.sessions,
              sub: started ? `${Math.round((f.sessions / started) * 100)}%` : undefined,
            }))}
          />
        </div>
        <div className="card p-4">
          <h2 className="mb-4 font-semibold">Popular packages</h2>
          <Bars rows={d.packages.map((p) => ({ label: p.name, value: p.bookings, sub: money(p.revenue) }))} />
        </div>
        <div className="card p-4">
          <h2 className="mb-4 font-semibold">Occasions</h2>
          <Bars rows={d.occasions.map((o) => ({ label: o.name, value: o.bookings }))} />
          <h3 className="mb-2 mt-6 text-sm font-semibold">Booked via</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(d.channels).map(([c, n]) => (
              <span key={c} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs dark:bg-slate-800">
                {titleCase(c)} · {n}
              </span>
            ))}
            {Object.keys(d.channels).length === 0 && <span className="text-sm text-slate-500">—</span>}
          </div>
          {Object.keys(d.kiosk_sessions.abandoned).length > 0 && (
            <>
              <h3 className="mb-2 mt-6 text-sm font-semibold">Kiosk sessions that ended without booking</h3>
              <ul className="space-y-1 text-sm">
                {Object.entries(d.kiosk_sessions.abandoned).map(([reason, n]) => (
                  <li key={reason} className="flex justify-between">
                    <span>{titleCase(reason)}</span>
                    <span className="tabular-nums text-slate-500">{n}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function DayChart({ rows, from, to }: { rows: Dashboard["by_day"]; from: string; to: string }) {
  const byDate = new Map(rows.map((r) => [r.date, r]));
  const days: string[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) days.push(d);
  const max = Math.max(1, ...rows.map((r) => r.bookings));
  return (
    <div>
      <div className="flex h-40 items-end gap-[2px]">
        {days.map((d) => {
          const r = byDate.get(d);
          const h = r ? Math.max(4, (r.bookings / max) * 100) : 0;
          return (
            <div key={d} className="group relative flex h-full flex-1 items-end">
              <div
                className="w-full rounded-t bg-brand-500 transition group-hover:bg-brand-700"
                style={{ height: `${h}%` }}
              />
              <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded bg-slate-900 px-2 py-1 text-xs text-white group-hover:block">
                {dateLabel(d)}: {r?.bookings ?? 0} bookings · {money(r?.revenue ?? 0)}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-xs text-slate-500">
        <span>{dateLabel(from)}</span>
        <span>{dateLabel(to)}</span>
      </div>
    </div>
  );
}
