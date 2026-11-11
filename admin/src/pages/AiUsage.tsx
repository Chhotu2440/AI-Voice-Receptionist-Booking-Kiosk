import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Empty, ErrorBox, Loading, PageHeader, Stat } from "../components/ui";
import { api, qs } from "../lib/api";
import { useAuth } from "../lib/auth";
import { addDays, dateLabel, money, todayIST, usd } from "../lib/format";
import type { AiSettings, AiUsage } from "../lib/types";

export function AiUsagePage() {
  const { can } = useAuth();
  const to = todayIST();
  const from = addDays(to, -29);
  const q = useQuery({
    queryKey: ["ai-usage", from, to],
    queryFn: () => api<AiUsage>(`/admin/ai/usage${qs({ from, to })}`),
    refetchInterval: 60_000,
  });

  return (
    <>
      <PageHeader title="AI & voice cost" subtitle="Measured from each voice session's real token usage, last 30 days." />
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <ErrorBox error={q.error} />
      ) : (
        <div className="space-y-6">
          {!q.data.caps.voice_allowed && (
            <div className="rounded-lg border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200">
              Voice is paused: {q.data.caps.reason}. Kiosks still take bookings by touch. Raise the cap below or wait for the
              next day/month.
            </div>
          )}
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Voice sessions" value={q.data.voice_sessions} hint={`${q.data.voice_bookings} ended in a booking`} />
            <Stat label="Cost · 30 days" value={money(q.data.cost_inr)} hint={usd(q.data.cost_usd)} />
            <Stat label="Per session" value={q.data.cost_per_session_usd ? usd(q.data.cost_per_session_usd, 3) : "—"} />
            <Stat label="Per voice booking" value={q.data.cost_per_booking_inr ? money(q.data.cost_per_booking_inr) : "—"} />
          </section>
          <section className="grid gap-4 sm:grid-cols-2">
            <CapBar label="Today" used={q.data.caps.today_usd} cap={q.data.caps.daily_cap_usd} />
            <CapBar label="This month" used={q.data.caps.month_usd} cap={q.data.caps.monthly_cap_usd} />
          </section>
          <section className="card overflow-hidden">
            <h2 className="border-b border-slate-200 px-4 py-3 font-semibold dark:border-slate-800">By day</h2>
            {q.data.by_day.length === 0 ? (
              <Empty>No voice sessions in this period.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-50 dark:bg-slate-900/60">
                    <tr>
                      <th className="th">Date</th>
                      <th className="th">Provider</th>
                      <th className="th">Sessions</th>
                      <th className="th">Minutes</th>
                      <th className="th">Cost</th>
                      <th className="th" title="Times the AI tried to act on noise and was stopped">Noise actions blocked</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {[...q.data.by_day].reverse().map((r) => (
                      <tr key={`${r.date}-${r.provider}`}>
                        <td className="td">{dateLabel(r.date)}</td>
                        <td className="td capitalize">{r.provider}</td>
                        <td className="td tabular-nums">{r.sessions}</td>
                        <td className="td tabular-nums">{r.minutes}</td>
                        <td className="td tabular-nums">{usd(r.cost_usd, 3)}</td>
                        <td className="td tabular-nums">{r.phantom_answers_blocked}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          {can("ai.config") ? <BudgetForm /> : <p className="text-sm text-slate-500">Only the owner can change the voice budget.</p>}
        </div>
      )}
    </>
  );
}

function CapBar({ label, used, cap }: { label: string; used: string; cap: string }) {
  const pct = Number(cap) > 0 ? Math.min(100, (Number(used) / Number(cap)) * 100) : 0;
  return (
    <div className="card p-4">
      <div className="flex justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-slate-500">
          {usd(used)} of {Number(cap) > 0 ? usd(cap, 0) : "no cap"}
        </span>
      </div>
      <div className="mt-2 h-2.5 rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className={`h-2.5 rounded-full ${pct >= 90 ? "bg-rose-500" : pct >= 70 ? "bg-amber-500" : "bg-emerald-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function BudgetForm() {
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["settings", "ai"], queryFn: () => api<AiSettings>("/admin/settings/ai") });
  const [daily, setDaily] = useState("");
  const [monthly, setMonthly] = useState("");
  const [rate, setRate] = useState("");
  useEffect(() => {
    if (s.data) {
      setDaily(s.data.daily_cap_usd);
      setMonthly(s.data.monthly_cap_usd);
      setRate(s.data.usd_inr);
    }
  }, [s.data]);
  const m = useMutation({
    mutationFn: () =>
      api<AiSettings>("/admin/settings/ai", {
        method: "PUT",
        body: { ...s.data, daily_cap_usd: daily, monthly_cap_usd: monthly, usd_inr: rate },
      }),
    onSuccess: (data) => {
      qc.setQueryData(["settings", "ai"], data);
      void qc.invalidateQueries({ queryKey: ["ai-usage"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  if (s.isPending) return <Loading />;
  if (s.isError) return <ErrorBox error={s.error} />;
  return (
    <section className="card p-4">
      <h2 className="font-semibold">Voice budget</h2>
      <p className="mb-4 text-sm text-slate-500">
        When a cap is reached, voice switches off and kiosks continue by touch. 0 means no cap. Prices are from{" "}
        {s.data.price_version}.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className="label" htmlFor="cap-daily">Daily cap (USD)</label>
          <input id="cap-daily" className="input" type="number" min={0} step="1" value={daily} onChange={(e) => setDaily(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="cap-monthly">Monthly cap (USD)</label>
          <input id="cap-monthly" className="input" type="number" min={0} step="1" value={monthly} onChange={(e) => setMonthly(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="usd-inr">USD → INR rate</label>
          <input id="usd-inr" className="input" type="number" min={1} step="0.5" value={rate} onChange={(e) => setRate(e.target.value)} />
        </div>
      </div>
      <div className="mt-4 flex items-center justify-end gap-3">
        <ErrorBox error={m.error} />
        {m.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
        <button className="btn-primary" disabled={m.isPending} onClick={() => m.mutate()}>Save budget</button>
      </div>
    </section>
  );
}
