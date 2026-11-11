import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { Badge, Drawer, Empty, ErrorBox, Loading, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateLabel, money, titleCase, todayIST } from "../lib/format";
import type { PackageFull, Page, PriceQuote, PricingRule, PricingSettings, RuleType } from "../lib/types";

const DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
const RULE_HELP: Record<Exclude<RuleType, "BASE_DAYTYPE">, { label: string; help: string; kind: "price" | "discount" }> = {
  DATE_OVERRIDE: { label: "Special price for one date", help: "e.g. Diwali or New Year's Eve. Beats the weekday/weekend price.", kind: "price" },
  DATE_RANGE: { label: "Special price for a date range", help: "e.g. summer holidays. Beats the weekday/weekend price.", kind: "price" },
  PROMO: { label: "Promotion (% off)", help: "Automatic, or only with a promo code if you set one.", kind: "discount" },
  GROUP_DISCOUNT: { label: "Group discount (% off)", help: "Applies when the group has at least the minimum players.", kind: "discount" },
};

function usePackages() {
  return useQuery({ queryKey: ["admin-packages"], queryFn: () => api<Page<PackageFull>>("/admin/packages?page_size=100") });
}
function useRules() {
  return useQuery({
    queryKey: ["pricing-rules"],
    queryFn: () => api<Page<PricingRule>>("/admin/pricing-rules?include_inactive=true&page_size=100"),
  });
}

export function PricingPage() {
  return (
    <>
      <PageHeader
        title="Pricing"
        subtitle="Prices are per player. The kiosk, voice assistant and front desk all use these; customers keep the price they were quoted."
      />
      <div className="space-y-6">
        <PreviewCard />
        <BasePrices />
        <SpecialRules />
        <TaxAndCharges />
      </div>
    </>
  );
}

/** Weekday / weekend price per package (BASE_DAYTYPE rules), edited as a grid. */
function BasePrices() {
  const qc = useQueryClient();
  const packages = usePackages();
  const rules = useRules();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: async () => {
      for (const [key, value] of Object.entries(drafts)) {
        const [pkgId, dayType] = key.split(":") as [string, "WEEKDAY" | "WEEKEND"];
        const existing = baseRule(rules.data?.items ?? [], pkgId, dayType);
        if (existing) {
          await api(`/admin/pricing-rules/${existing.id}`, {
            method: "PATCH",
            body: { price_per_person: value, ...(existing.is_active ? {} : { is_active: true }) },
          });
        } else {
          await api("/admin/pricing-rules", {
            method: "POST",
            body: { rule_type: "BASE_DAYTYPE", package_id: pkgId, day_type: dayType, price_per_person: value, name: `${titleCase(dayType)} price` },
          });
        }
      }
    },
    onSuccess: () => {
      setDrafts({});
      void qc.invalidateQueries({ queryKey: ["pricing-rules"] });
      void qc.invalidateQueries({ queryKey: ["price-preview"] });
      void qc.invalidateQueries({ queryKey: ["packages-public"] });
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ["pricing-rules"] }),
  });

  if (packages.isPending || rules.isPending) return <div className="card"><Loading /></div>;
  if (packages.isError || rules.isError) return <ErrorBox error={packages.error ?? rules.error} />;
  const dirty = Object.keys(drafts).length > 0;
  const invalid = Object.values(drafts).some((v) => v === "" || Number(v) < 0 || Number.isNaN(Number(v)));

  return (
    <section className="card overflow-hidden">
      <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 className="font-semibold">Regular prices (per player)</h2>
        <p className="text-sm text-slate-500">Weekend days are set under Tax &amp; charges below.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-slate-50 dark:bg-slate-900/60">
            <tr>
              <th className="th">Package</th>
              <th className="th">Weekday ₹</th>
              <th className="th">Weekend ₹</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {packages.data.items.filter((p) => p.is_active).sort((a, b) => a.sort_order - b.sort_order).map((p) => (
              <tr key={p.id}>
                <td className="td font-medium">{p.name_en}</td>
                {(["WEEKDAY", "WEEKEND"] as const).map((dt) => {
                  const key = `${p.id}:${dt}`;
                  const rule = baseRule(rules.data.items, p.id, dt);
                  const current = rule?.is_active ? String(Number(rule.price_per_person)) : "";
                  return (
                    <td key={dt} className="td">
                      <input
                        aria-label={`${p.name_en} ${dt.toLowerCase()} price`}
                        type="number"
                        min={0}
                        step="1"
                        className={`input w-32 tabular-nums ${!current && !(key in drafts) ? "border-amber-400" : ""}`}
                        placeholder="Not set"
                        value={drafts[key] ?? current}
                        onChange={(e) => setDrafts((prev) => {
                          const next = { ...prev };
                          if (e.target.value === current) delete next[key];
                          else next[key] = e.target.value;
                          return next;
                        })}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-end gap-3 border-t border-slate-200 px-4 py-3 dark:border-slate-800">
        <ErrorBox error={save.error} />
        {save.isSuccess && !dirty && <span className="text-sm text-emerald-600">Saved.</span>}
        {dirty && <button className="btn-secondary" onClick={() => setDrafts({})}>Discard</button>}
        <button className="btn-primary" disabled={!dirty || invalid || save.isPending} onClick={() => save.mutate()} data-testid="save-base-prices">
          Save prices
        </button>
      </div>
    </section>
  );
}

function baseRule(rules: PricingRule[], pkgId: string, dayType: "WEEKDAY" | "WEEKEND"): PricingRule | undefined {
  return rules
    .filter((r) => r.rule_type === "BASE_DAYTYPE" && r.package_id === pkgId && r.day_type === dayType)
    .sort((a, b) => Number(b.is_active) - Number(a.is_active) || b.priority - a.priority)[0];
}

function SpecialRules() {
  const qc = useQueryClient();
  const packages = usePackages();
  const rules = useRules();
  const [editing, setEditing] = useState<PricingRule | "new" | null>(null);
  const [showOld, setShowOld] = useState(false);
  const toggle = useMutation({
    mutationFn: (r: PricingRule) =>
      r.is_active
        ? api(`/admin/pricing-rules/${r.id}`, { method: "DELETE" })
        : api(`/admin/pricing-rules/${r.id}`, { method: "PATCH", body: { is_active: true } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["pricing-rules"] });
      void qc.invalidateQueries({ queryKey: ["price-preview"] });
    },
  });
  const pkgName = (id: string | null) => (id ? packages.data?.items.find((p) => p.id === id)?.name_en ?? "Deleted package" : "All packages");
  const items = (rules.data?.items ?? []).filter((r) => r.rule_type !== "BASE_DAYTYPE" && (showOld || r.is_active));

  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div>
          <h2 className="font-semibold">Special prices &amp; discounts</h2>
          <p className="text-sm text-slate-500">Festival prices, holiday seasons, promotions and group discounts.</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={showOld} onChange={(e) => setShowOld(e.target.checked)} />
            Show switched-off
          </label>
          <button className="btn-primary" onClick={() => setEditing("new")} data-testid="add-rule">+ Add</button>
        </div>
      </div>
      {rules.isPending ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty>None yet.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {items.map((r) => (
                <tr key={r.id} className={r.is_active ? "" : "opacity-60"} data-testid={`rule-${r.name}`}>
                  <td className="td">
                    <div className="font-medium">{r.name || RULE_HELP[r.rule_type as keyof typeof RULE_HELP].label}</div>
                    <div className="text-xs text-slate-500">{describeRule(r, pkgName(r.package_id))}</div>
                  </td>
                  <td className="td whitespace-nowrap text-right font-medium tabular-nums">
                    {r.price_per_person ? `${money(r.price_per_person)} / player` : `${Number(r.discount_pct)}% off`}
                  </td>
                  <td className="td">{r.is_active ? <Badge status="ACTIVE" label="On" /> : <Badge status="DISABLED" label="Off" />}</td>
                  <td className="td text-right">
                    <div className="flex justify-end gap-2">
                      <button className="btn-secondary" onClick={() => setEditing(r)}>Edit</button>
                      <button className="btn-secondary" disabled={toggle.isPending} onClick={() => toggle.mutate(r)}>
                        {r.is_active ? "Switch off" : "Switch on"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {toggle.isError && <div className="p-4"><ErrorBox error={toggle.error} /></div>}
      {editing && <RuleEditor rule={editing === "new" ? null : editing} packages={packages.data?.items ?? []} onClose={() => setEditing(null)} />}
    </section>
  );
}

function describeRule(r: PricingRule, pkg: string): string {
  const parts = [pkg];
  if (r.rule_type === "DATE_OVERRIDE" && r.date_from) parts.push(dateLabel(r.date_from));
  if (r.rule_type !== "DATE_OVERRIDE" && (r.date_from || r.date_to))
    parts.push(`${r.date_from ? dateLabel(r.date_from) : "…"} – ${r.date_to ? dateLabel(r.date_to) : "…"}`);
  if (r.day_type) parts.push(`${titleCase(r.day_type)}s only`);
  if (r.min_guests) parts.push(`${r.min_guests}+ players`);
  if (r.rule_type === "PROMO") parts.push(r.promo_code ? `code ${r.promo_code}` : "automatic");
  return parts.join(" · ");
}

function RuleEditor({ rule, packages, onClose }: { rule: PricingRule | null; packages: PackageFull[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState<Exclude<RuleType, "BASE_DAYTYPE">>((rule?.rule_type as Exclude<RuleType, "BASE_DAYTYPE">) ?? "DATE_OVERRIDE");
  const [name, setName] = useState(rule?.name ?? "");
  const [pkg, setPkg] = useState(rule?.package_id ?? "");
  const [from, setFrom] = useState(rule?.date_from ?? "");
  const [to, setTo] = useState(rule?.date_to ?? "");
  const [dayType, setDayType] = useState(rule?.day_type ?? "");
  const [minGuests, setMinGuests] = useState(rule?.min_guests ? String(rule.min_guests) : "");
  const [code, setCode] = useState(rule?.promo_code ?? "");
  const [value, setValue] = useState(rule ? String(Number(rule.price_per_person ?? rule.discount_pct ?? "")) : "");
  const kind = RULE_HELP[type].kind;

  const m = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name: name.trim(),
        day_type: dayType || null,
        date_from: from || null,
        date_to: type === "DATE_OVERRIDE" ? null : to || null,
        min_guests: minGuests ? Number(minGuests) : null,
        promo_code: type === "PROMO" && code.trim() ? code.trim().toUpperCase() : null,
        price_per_person: kind === "price" ? value : null,
        discount_pct: kind === "discount" ? value : null,
      };
      if (rule) return api(`/admin/pricing-rules/${rule.id}`, { method: "PATCH", body });
      return api("/admin/pricing-rules", { method: "POST", body: { ...body, rule_type: type, package_id: pkg || null } });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["pricing-rules"] });
      void qc.invalidateQueries({ queryKey: ["price-preview"] });
      onClose();
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    m.mutate();
  }

  return (
    <Drawer open onClose={onClose} title={rule ? "Edit special price or discount" : "Add special price or discount"}>
      <form className="space-y-4 text-sm" onSubmit={submit}>
        <fieldset disabled={!!rule}>
          <legend className="label">Type</legend>
          <div className="space-y-1.5">
            {(Object.keys(RULE_HELP) as (keyof typeof RULE_HELP)[]).map((t) => (
              <label key={t} className={`flex cursor-pointer gap-2 rounded-lg border p-2 ${type === t ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20" : "border-slate-200 dark:border-slate-700"}`}>
                <input type="radio" name="rule-type" className="mt-0.5 accent-brand-600" checked={type === t} onChange={() => setType(t)} />
                <span><span className="font-medium">{RULE_HELP[t].label}</span><span className="block text-xs text-slate-500">{RULE_HELP[t].help}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
        <div>
          <label className="label" htmlFor="r-name">Name (staff only)</label>
          <input id="r-name" className="input" maxLength={100} required placeholder="e.g. Diwali 2026" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="r-pkg">Package</label>
          <select id="r-pkg" className="input" disabled={!!rule} value={pkg} onChange={(e) => setPkg(e.target.value)}>
            <option value="">All packages</option>
            {packages.map((p) => <option key={p.id} value={p.id}>{p.name_en}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="r-from">{type === "DATE_OVERRIDE" ? "Date" : "From (optional)"}</label>
            <input id="r-from" type="date" className="input" required={type !== "PROMO" && type !== "GROUP_DISCOUNT"} value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          {type !== "DATE_OVERRIDE" && (
            <div>
              <label className="label" htmlFor="r-to">{type === "DATE_RANGE" ? "To" : "To (optional)"}</label>
              <input id="r-to" type="date" className="input" min={from || undefined} required={type === "DATE_RANGE"} value={to} onChange={(e) => setTo(e.target.value)} />
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="r-day">Days</label>
            <select id="r-day" className="input" value={dayType} onChange={(e) => setDayType(e.target.value as "" | "WEEKDAY" | "WEEKEND")}>
              <option value="">Every day</option>
              <option value="WEEKDAY">Weekdays only</option>
              <option value="WEEKEND">Weekends only</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="r-min">Min players {type === "GROUP_DISCOUNT" ? "" : "(optional)"}</label>
            <input id="r-min" type="number" min={1} className="input" required={type === "GROUP_DISCOUNT"} value={minGuests} onChange={(e) => setMinGuests(e.target.value)} />
          </div>
        </div>
        {type === "PROMO" && (
          <div>
            <label className="label" htmlFor="r-code">Promo code (optional)</label>
            <input id="r-code" className="input font-mono uppercase" pattern="[A-Za-z0-9_\-]{3,32}" placeholder="Leave empty for an automatic promotion" value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
        )}
        <div>
          <label className="label" htmlFor="r-value">{kind === "price" ? "Price per player (₹)" : "Discount (%)"}</label>
          <input id="r-value" type="number" className="input w-40" required min={kind === "price" ? 0 : 0.01} max={kind === "price" ? undefined : 100} step={kind === "price" ? "1" : "0.5"} value={value} onChange={(e) => setValue(e.target.value)} />
        </div>
        <ErrorBox error={m.error} />
        <div className="flex justify-end gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={m.isPending} data-testid="save-rule">Save</button>
        </div>
      </form>
    </Drawer>
  );
}

function TaxAndCharges() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const s = useQuery({ queryKey: ["settings", "pricing"], queryFn: () => api<PricingSettings>("/admin/settings/pricing") });
  const [d, setD] = useState<PricingSettings | null>(null);
  useEffect(() => {
    if (s.data) setD(s.data);
  }, [s.data]);
  const m = useMutation({
    mutationFn: () => api<PricingSettings>("/admin/settings/pricing", { method: "PUT", body: d }),
    onSuccess: (data) => {
      qc.setQueryData(["settings", "pricing"], data);
      void qc.invalidateQueries({ queryKey: ["price-preview"] });
      void qc.invalidateQueries({ queryKey: ["packages-public"] });
    },
  });
  if (s.isPending || !d) return <div className="card"><Loading /></div>;
  if (s.isError) return <ErrorBox error={s.error} />;
  const editable = can("pricing.write");

  return (
    <section className="card p-4">
      <h2 className="font-semibold">Tax &amp; charges</h2>
      <p className="mb-4 text-sm text-slate-500">Applies to new quotes only; existing bookings keep their price.</p>
      <fieldset disabled={!editable} className="space-y-5 text-sm">
        <div>
          <span className="label">Weekend days (weekend prices apply)</span>
          <div className="flex flex-wrap gap-2">
            {DAYS.map((day) => {
              const on = d.weekend_days.includes(day);
              return (
                <button
                  type="button"
                  key={day}
                  aria-pressed={on}
                  onClick={() => setD({ ...d, weekend_days: on ? d.weekend_days.filter((x) => x !== day) : [...d.weekend_days, day] })}
                  className={`rounded-lg border px-3 py-1.5 ${on ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300 dark:border-slate-700"}`}
                >
                  {titleCase(day)}
                </button>
              );
            })}
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="label" htmlFor="tax-rate">GST rate (%)</label>
            <input id="tax-rate" type="number" min={0} max={100} step="0.01" className="input" value={d.tax_rate} onChange={(e) => setD({ ...d, tax_rate: e.target.value })} />
          </div>
          <div>
            <span className="label">Prices entered…</span>
            <select aria-label="Prices include tax" className="input" value={d.prices_include_tax ? "incl" : "excl"} onChange={(e) => setD({ ...d, prices_include_tax: e.target.value === "incl" })}>
              <option value="incl">include GST</option>
              <option value="excl">exclude GST (added on top)</option>
            </select>
          </div>
          <div>
            <span className="label">When several discounts apply</span>
            <select aria-label="Discount stacking" className="input" value={d.discount_stacking} onChange={(e) => setD({ ...d, discount_stacking: e.target.value as "BEST" | "STACK" })}>
              <option value="BEST">give only the biggest one</option>
              <option value="STACK">combine them</option>
            </select>
          </div>
        </div>
        <div>
          <span className="label">Extra charges</span>
          <div className="space-y-2">
            {d.extra_charges.map((c, i) => (
              <div key={i} className="flex flex-wrap gap-2">
                <input aria-label="Charge name" className="input max-w-xs" placeholder="e.g. Socks" value={c.label} onChange={(e) => setD({ ...d, extra_charges: d.extra_charges.map((x, j) => (j === i ? { ...x, label: e.target.value, code: x.code || codeFrom(e.target.value) } : x)) })} />
                <select aria-label="Charge mode" className="input w-40" value={c.mode} onChange={(e) => setD({ ...d, extra_charges: d.extra_charges.map((x, j) => (j === i ? { ...x, mode: e.target.value as "FLAT" | "PER_PERSON" } : x)) })}>
                  <option value="PER_PERSON">per player</option>
                  <option value="FLAT">per booking</option>
                </select>
                <input aria-label="Charge amount" type="number" min={0} className="input w-28" value={c.amount} onChange={(e) => setD({ ...d, extra_charges: d.extra_charges.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)) })} />
                <button type="button" className="btn-secondary" aria-label="Remove charge" onClick={() => setD({ ...d, extra_charges: d.extra_charges.filter((_, j) => j !== i) })}>✕</button>
              </div>
            ))}
            {d.extra_charges.length < 10 && (
              <button type="button" className="btn-secondary" onClick={() => setD({ ...d, extra_charges: [...d.extra_charges, { code: "", label: "", mode: "PER_PERSON", amount: "0" }] })}>
                + Add charge
              </button>
            )}
          </div>
        </div>
      </fieldset>
      {editable && (
        <div className="mt-4 flex items-center justify-end gap-3">
          <ErrorBox error={m.error} />
          {m.isSuccess && <span className="text-sm text-emerald-600">Saved.</span>}
          <button className="btn-primary" disabled={m.isPending || JSON.stringify(d) === JSON.stringify(s.data)} onClick={() => m.mutate()}>
            Save tax &amp; charges
          </button>
        </div>
      )}
    </section>
  );
}

function codeFrom(label: string): string {
  return label.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 32) || "CHARGE";
}

/** Ask the real pricing engine what a customer would pay. */
function PreviewCard() {
  const packages = usePackages();
  const [pkg, setPkg] = useState("");
  const [date, setDate] = useState(todayIST());
  const [guests, setGuests] = useState(6);
  const [promo, setPromo] = useState("");
  const active = packages.data?.items.filter((p) => p.is_active) ?? [];
  useEffect(() => {
    if (!pkg && active[0]) setPkg(active[0].id);
  }, [pkg, active]);
  const q = useQuery({
    queryKey: ["price-preview", pkg, date, guests, promo],
    queryFn: () =>
      api<PriceQuote>("/admin/pricing/preview", {
        method: "POST",
        body: { package_id: pkg, date, guest_count: guests, promo_code: promo.trim() || null },
      }),
    enabled: !!pkg && !!date && guests > 0,
    retry: false,
  });

  return (
    <section className="card p-4" data-testid="price-preview">
      <h2 className="font-semibold">Price check</h2>
      <p className="mb-4 text-sm text-slate-500">See exactly what a customer would be quoted, with your saved prices.</p>
      <div className="grid gap-3 sm:grid-cols-4">
        <div>
          <label className="label" htmlFor="pv-pkg">Package</label>
          <select id="pv-pkg" className="input" value={pkg} onChange={(e) => setPkg(e.target.value)}>
            {active.map((p) => <option key={p.id} value={p.id}>{p.name_en}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="pv-date">Date</label>
          <input id="pv-date" type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="pv-guests">Players</label>
          <input id="pv-guests" type="number" min={1} className="input" value={guests} onChange={(e) => setGuests(Number(e.target.value))} />
        </div>
        <div>
          <label className="label" htmlFor="pv-promo">Promo code</label>
          <input id="pv-promo" className="input uppercase" value={promo} onChange={(e) => setPromo(e.target.value)} />
        </div>
      </div>
      <div className="mt-4">
        {q.isFetching && !q.data ? (
          <Loading label="Calculating…" />
        ) : q.isError ? (
          <ErrorBox error={q.error} />
        ) : q.data ? (
          <div className="flex flex-wrap items-baseline justify-between gap-4 rounded-lg bg-slate-50 p-4 dark:bg-slate-800/60">
            <div className="space-y-0.5 text-sm">
              <div>{q.data.guest_count} × {money(q.data.price_per_person)} ({titleCase(q.data.day_type)}) = {money(q.data.subtotal)}</div>
              {q.data.discounts.map((d) => <div key={d.rule_id} className="text-emerald-600">{d.name}: −{money(d.amount)} ({Number(d.pct)}%)</div>)}
              {q.data.charges.map((c) => <div key={c.code}>{c.label}: {money(c.amount)}</div>)}
              <div className="text-slate-500">GST {Number(q.data.tax.rate)}% {q.data.tax.included ? "included" : "added"}: {money(q.data.tax.amount)}</div>
            </div>
            <div className="text-right">
              <div className="text-xs uppercase tracking-wide text-slate-500">Customer pays</div>
              <div className="text-3xl font-semibold tabular-nums" data-testid="preview-total">{money(q.data.total)}</div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
