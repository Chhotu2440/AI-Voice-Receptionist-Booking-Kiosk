import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Badge, Drawer, Empty, ErrorBox, Loading, Modal, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import type { OccasionFull, PackageFull, Page } from "../lib/types";

type Draft = Omit<PackageFull, "id">;

const EMPTY: Draft = {
  code: "",
  name_en: "",
  name_hi: "",
  description_en: "",
  description_hi: "",
  duration_min: 30,
  games_count: null,
  formats_count: null,
  min_guests: 1,
  max_guests: 20,
  is_recommended: false,
  sort_order: 0,
  is_active: true,
  features: [],
};

export function PackagesPage() {
  const list = useQuery({
    queryKey: ["admin-packages"],
    queryFn: () => api<Page<PackageFull>>("/admin/packages?page_size=100"),
  });
  const [editing, setEditing] = useState<PackageFull | "new" | null>(null);
  const [removing, setRemoving] = useState<PackageFull | null>(null);

  return (
    <>
      <PageHeader
        title="Packages"
        subtitle="What customers can book on the kiosk. Prices are set on the Pricing page."
        actions={<button className="btn-primary" onClick={() => setEditing("new")} data-testid="add-package">+ New package</button>}
      />
      <div className="card overflow-hidden">
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <div className="p-4"><ErrorBox error={list.error} /></div>
        ) : list.data.items.length === 0 ? (
          <Empty>No packages yet.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/60">
                <tr>
                  <th className="th">Package</th>
                  <th className="th">Duration</th>
                  <th className="th">Players</th>
                  <th className="th">Kiosk</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {[...list.data.items].sort((a, b) => a.sort_order - b.sort_order).map((p) => (
                  <tr key={p.id} data-testid={`package-row-${p.code}`}>
                    <td className="td">
                      <div className="font-medium">
                        {p.name_en}
                        {p.is_recommended && <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">Recommended</span>}
                      </div>
                      <div className="text-xs text-slate-500">{p.code}{p.name_hi && ` · ${p.name_hi}`}</div>
                    </td>
                    <td className="td text-sm">{p.duration_min} min{p.games_count ? ` · ${p.games_count} games` : ""}</td>
                    <td className="td text-sm tabular-nums">{p.min_guests}–{p.max_guests}</td>
                    <td className="td">{p.is_active ? <Badge status="ACTIVE" label="Shown" /> : <Badge status="DISABLED" label="Hidden" />}</td>
                    <td className="td text-right">
                      <div className="flex justify-end gap-2">
                        <button className="btn-secondary" onClick={() => setEditing(p)}>Edit</button>
                        <button className="btn-secondary" onClick={() => setRemoving(p)}>Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <OccasionsSection />
      {editing && <PackageEditor pkg={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {removing && <DeleteModal pkg={removing} onClose={() => setRemoving(null)} />}
    </>
  );
}

function PackageEditor({ pkg, onClose }: { pkg: PackageFull | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [d, setD] = useState<Draft>(() => (pkg ? { ...pkg, features: pkg.features.map((f) => ({ ...f })) } : EMPTY));
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((prev) => ({ ...prev, [k]: v }));
  const m = useMutation({
    mutationFn: () => {
      const { code, ...fields } = d;
      const body = { ...fields, features: d.features.filter((f) => f.text_en.trim()) };
      return pkg
        ? api<PackageFull>(`/admin/packages/${pkg.id}`, { method: "PATCH", body })
        : api<PackageFull>("/admin/packages", { method: "POST", body: { ...body, code: code.trim().toUpperCase() } });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-packages"] });
      void qc.invalidateQueries({ queryKey: ["packages-public"] });
      onClose();
    },
  });
  const num = (v: string) => (v === "" ? null : Number(v));

  function submit(e: FormEvent) {
    e.preventDefault();
    m.mutate();
  }

  return (
    <Drawer open onClose={onClose} title={pkg ? `Edit ${pkg.name_en}` : "New package"} wide>
      <form className="space-y-5 text-sm" onSubmit={submit}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="p-name-en">Name (English)</label>
            <input id="p-name-en" className="input" required maxLength={80} value={d.name_en} onChange={(e) => set("name_en", e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="p-name-hi">Name (Hindi)</label>
            <input id="p-name-hi" className="input" maxLength={80} value={d.name_hi} onChange={(e) => set("name_hi", e.target.value)} />
          </div>
          {!pkg && (
            <div>
              <label className="label" htmlFor="p-code">Code</label>
              <input id="p-code" className="input font-mono uppercase" required pattern="[A-Za-z0-9_]{2,32}" placeholder="e.g. PARTY_PACK" value={d.code} onChange={(e) => set("code", e.target.value)} />
              <p className="mt-1 text-xs text-slate-500">Letters, numbers and _ only. Can't be changed later.</p>
            </div>
          )}
          <div>
            <label className="label" htmlFor="p-sort">Order on kiosk</label>
            <input id="p-sort" type="number" min={0} max={1000} className="input" value={d.sort_order} onChange={(e) => set("sort_order", Number(e.target.value))} />
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="p-desc-en">Description (English)</label>
            <textarea id="p-desc-en" className="input min-h-[80px]" maxLength={2000} value={d.description_en} onChange={(e) => set("description_en", e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="p-desc-hi">Description (Hindi)</label>
            <textarea id="p-desc-hi" className="input min-h-[80px]" maxLength={2000} value={d.description_hi} onChange={(e) => set("description_hi", e.target.value)} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <div>
            <label className="label" htmlFor="p-duration">Minutes</label>
            <input id="p-duration" type="number" min={5} max={480} required className="input" value={d.duration_min} onChange={(e) => set("duration_min", Number(e.target.value))} />
          </div>
          <div>
            <label className="label" htmlFor="p-games">Games</label>
            <input id="p-games" type="number" min={1} max={100} className="input" value={d.games_count ?? ""} onChange={(e) => set("games_count", num(e.target.value))} />
          </div>
          <div>
            <label className="label" htmlFor="p-formats">Formats</label>
            <input id="p-formats" type="number" min={1} max={100} className="input" value={d.formats_count ?? ""} onChange={(e) => set("formats_count", num(e.target.value))} />
          </div>
          <div>
            <label className="label" htmlFor="p-min">Min players</label>
            <input id="p-min" type="number" min={1} max={1000} required className="input" value={d.min_guests} onChange={(e) => set("min_guests", Number(e.target.value))} />
          </div>
          <div>
            <label className="label" htmlFor="p-max">Max players</label>
            <input id="p-max" type="number" min={1} max={1000} required className="input" value={d.max_guests} onChange={(e) => set("max_guests", Number(e.target.value))} />
          </div>
        </div>
        <div className="flex flex-wrap gap-6">
          <label className="flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={d.is_active} onChange={(e) => set("is_active", e.target.checked)} />
            Show on kiosk
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={d.is_recommended} onChange={(e) => set("is_recommended", e.target.checked)} />
            Mark as recommended
          </label>
        </div>

        <fieldset>
          <legend className="label">What's included (shown as bullet points)</legend>
          <div className="space-y-2">
            {d.features.map((f, i) => (
              <div key={i} className="flex gap-2">
                <input
                  aria-label={`Feature ${i + 1} (English)`}
                  className="input"
                  maxLength={160}
                  placeholder="English"
                  value={f.text_en}
                  onChange={(e) => set("features", d.features.map((x, j) => (j === i ? { ...x, text_en: e.target.value } : x)))}
                />
                <input
                  aria-label={`Feature ${i + 1} (Hindi)`}
                  className="input"
                  maxLength={160}
                  placeholder="Hindi"
                  value={f.text_hi}
                  onChange={(e) => set("features", d.features.map((x, j) => (j === i ? { ...x, text_hi: e.target.value } : x)))}
                />
                <button type="button" className="btn-secondary" aria-label="Remove feature" onClick={() => set("features", d.features.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
            {d.features.length < 20 && (
              <button type="button" className="btn-secondary" onClick={() => set("features", [...d.features, { text_en: "", text_hi: "" }])}>
                + Add point
              </button>
            )}
          </div>
        </fieldset>
        <ErrorBox error={m.error} />
        <div className="flex justify-end gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={m.isPending} data-testid="save-package">{pkg ? "Save package" : "Create package"}</button>
        </div>
        {!pkg && <p className="text-xs text-slate-500">After creating it, set its weekday and weekend prices on the Pricing page; the kiosk can't sell a package without a price.</p>}
      </form>
    </Drawer>
  );
}

function DeleteModal({ pkg, onClose }: { pkg: PackageFull; onClose: () => void }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api<void>(`/admin/packages/${pkg.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-packages"] });
      onClose();
    },
  });
  return (
    <Modal open onClose={onClose} title={`Delete ${pkg.name_en}?`}>
      <p className="mb-3 text-sm text-slate-500">
        It disappears from the kiosk and this list. Existing bookings keep it. To hide it temporarily instead, edit it and untick
        "Show on kiosk".
      </p>
      <ErrorBox error={m.error} />
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Keep</button>
        <button className="btn-danger" disabled={m.isPending} onClick={() => m.mutate()}>Delete package</button>
      </div>
    </Modal>
  );
}

function OccasionsSection() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["admin-occasions"], queryFn: () => api<OccasionFull[]>("/admin/occasions") });
  const m = useMutation({
    mutationFn: ({ code, body }: { code: string; body: Partial<OccasionFull> }) =>
      api<OccasionFull>(`/admin/occasions/${code}`, { method: "PATCH", body }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-occasions"] });
      void qc.invalidateQueries({ queryKey: ["occasions"] });
    },
  });
  return (
    <section className="card mt-6 overflow-hidden">
      <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 className="font-semibold">Occasions</h2>
        <p className="text-sm text-slate-500">
          The "what's the occasion?" choices. "Needs a quote" sends customers to an event enquiry instead of booking directly.
        </p>
      </div>
      {list.isPending ? (
        <Loading />
      ) : list.isError ? (
        <div className="p-4"><ErrorBox error={list.error} /></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50 dark:bg-slate-900/60">
              <tr>
                <th className="th">English</th>
                <th className="th">Hindi</th>
                <th className="th">Needs a quote</th>
                <th className="th">Shown</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {[...list.data].sort((a, b) => a.sort_order - b.sort_order).map((o) => (
                <tr key={o.code}>
                  <td className="td">
                    <input
                      aria-label={`${o.code} English label`}
                      className="input"
                      defaultValue={o.label_en}
                      maxLength={64}
                      onBlur={(e) => e.target.value.trim() && e.target.value !== o.label_en && m.mutate({ code: o.code, body: { label_en: e.target.value.trim() } })}
                    />
                  </td>
                  <td className="td">
                    <input
                      aria-label={`${o.code} Hindi label`}
                      className="input"
                      defaultValue={o.label_hi}
                      maxLength={64}
                      onBlur={(e) => e.target.value !== o.label_hi && m.mutate({ code: o.code, body: { label_hi: e.target.value.trim() } })}
                    />
                  </td>
                  <td className="td">
                    <input type="checkbox" aria-label={`${o.code} needs a quote`} className="h-4 w-4 accent-brand-600" checked={o.always_enquiry} onChange={(e) => m.mutate({ code: o.code, body: { always_enquiry: e.target.checked } })} />
                  </td>
                  <td className="td">
                    <input type="checkbox" aria-label={`${o.code} shown`} className="h-4 w-4 accent-brand-600" checked={o.is_active} onChange={(e) => m.mutate({ code: o.code, body: { is_active: e.target.checked } })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {m.isError && <div className="p-4"><ErrorBox error={m.error} /></div>}
    </section>
  );
}
