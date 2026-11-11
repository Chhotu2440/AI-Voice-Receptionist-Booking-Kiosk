import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Badge, Drawer, Empty, ErrorBox, Loading, Modal, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { ago, dateTime } from "../lib/format";
import type { Kiosk } from "../lib/types";

type Pairing = { kiosk: Kiosk; pairing_code: string; expires_at: string };

/** Settings a manager may tune per kiosk. Keys match DEFAULT_CONFIG in kiosk_device_service. */
const CONFIG_FIELDS: { key: string; label: string; kind: "bool" | "number"; hint?: string; min?: number; max?: number; step?: number }[] = [
  { key: "voice_enabled", label: "Voice assistant", kind: "bool", hint: "Off = touch only" },
  { key: "volume", label: "Volume (%)", kind: "number", min: 0, max: 100, step: 5 },
  { key: "presence_enabled", label: "Wake on approach (camera)", kind: "bool", hint: "On-device only; no images leave the kiosk" },
  { key: "presence_min_face_area", label: "Face size to wake", kind: "number", min: 0.002, max: 0.2, step: 0.001, hint: "Smaller = wakes from further away" },
  { key: "presence_dwell_ms", label: "Look time before greeting (ms)", kind: "number", min: 300, max: 10000, step: 100 },
  { key: "presence_leave_ms", label: "Away time before reset (ms)", kind: "number", min: 3000, max: 120000, step: 1000 },
  { key: "idle_timeout_s", label: "Idle timeout (s)", kind: "number", min: 15, max: 600, step: 5 },
  { key: "success_reset_s", label: "Confirmation screen (s)", kind: "number", min: 5, max: 120, step: 1 },
];

export function KiosksPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["kiosks"], queryFn: () => api<Kiosk[]>("/admin/kiosks"), refetchInterval: 30_000 });
  const [adding, setAdding] = useState(false);
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const edit = list.data?.find((k) => k.id === editId) ?? null;

  const newCode = useMutation({
    mutationFn: (id: string) => api<Pairing>(`/admin/kiosks/${id}/pairing-code`, { method: "POST" }),
    onSuccess: (p) => {
      setPairing(p);
      void qc.invalidateQueries({ queryKey: ["kiosks"] });
    },
  });

  return (
    <>
      <PageHeader
        title="Kiosks"
        subtitle="Pair new kiosks, see which are online, and tune voice and camera settings."
        actions={<button className="btn-primary" onClick={() => setAdding(true)}>+ Pair a kiosk</button>}
      />
      <div className="card overflow-hidden">
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <div className="p-4"><ErrorBox error={list.error} /></div>
        ) : list.data.length === 0 ? (
          <Empty>No kiosks yet. Pair the first one.</Empty>
        ) : (
          <table className="w-full">
            <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/60">
              <tr>
                <th className="th">Kiosk</th>
                <th className="th">Status</th>
                <th className="th">Last check-in</th>
                <th className="th">App</th>
                <th className="th">Voice</th>
                <th className="th" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {list.data.map((k) => (
                <tr key={k.id}>
                  <td className="td">
                    <div className="flex items-center gap-2 font-medium">
                      <span className={`h-2.5 w-2.5 rounded-full ${k.online ? "bg-emerald-500" : "bg-slate-400"}`} title={k.online ? "Online" : "Offline"} />
                      {k.name}
                    </div>
                    <div className="text-xs text-slate-500">Paired {dateTime(k.paired_at)}</div>
                  </td>
                  <td className="td"><Badge status={k.status} /></td>
                  <td className="td text-sm">{k.online ? "Online" : "Offline"} · {ago(k.last_heartbeat_at)}</td>
                  <td className="td text-sm">{k.app_version ?? "—"}</td>
                  <td className="td text-sm">{k.config.voice_enabled ? "On" : "Off"}</td>
                  <td className="td text-right">
                    <div className="flex justify-end gap-2">
                      <button className="btn-secondary" onClick={() => setEditId(k.id)}>Settings</button>
                      <button className="btn-secondary" disabled={newCode.isPending} onClick={() => newCode.mutate(k.id)}>
                        New pairing code
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <ErrorBox error={newCode.error} />
      <AddKioskModal open={adding} onClose={() => setAdding(false)} onPaired={(p) => { setAdding(false); setPairing(p); }} />
      <Modal open={!!pairing} onClose={() => setPairing(null)} title={`Pairing code for ${pairing?.kiosk.name ?? ""}`}>
        <p className="text-sm text-slate-500">On the kiosk's setup screen, type this code. It works once and expires {dateTime(pairing?.expires_at)}.</p>
        <p className="my-5 text-center font-mono text-4xl font-semibold tracking-[0.3em]" data-testid="pairing-code">{pairing?.pairing_code}</p>
        <div className="flex justify-end"><button className="btn-primary" onClick={() => setPairing(null)}>Done</button></div>
      </Modal>
      <KioskSettings kiosk={edit} onClose={() => setEditId(null)} />
    </>
  );
}

function AddKioskModal({ open, onClose, onPaired }: { open: boolean; onClose: () => void; onPaired: (p: Pairing) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const m = useMutation({
    mutationFn: () => api<Pairing>("/admin/kiosks", { method: "POST", body: { name: name.trim() } }),
    onSuccess: (p) => {
      setName("");
      void qc.invalidateQueries({ queryKey: ["kiosks"] });
      onPaired(p);
    },
  });
  return (
    <Modal open={open} onClose={onClose} title="Pair a kiosk">
      <label className="label" htmlFor="kiosk-name">Name</label>
      <input id="kiosk-name" autoFocus className="input mb-3" placeholder="e.g. Entrance kiosk" value={name} onChange={(e) => setName(e.target.value)} />
      <ErrorBox error={m.error} />
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!name.trim() || m.isPending} onClick={() => m.mutate()}>Get pairing code</button>
      </div>
    </Modal>
  );
}

function KioskSettings({ kiosk, onClose }: { kiosk: Kiosk | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  useEffect(() => {
    if (kiosk) {
      setName(kiosk.name);
      setConfig(kiosk.config);
    }
    // Re-sync only when the saved values change (not on every 30 s list refresh, which would drop edits).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kiosk?.id, kiosk?.name, JSON.stringify(kiosk?.config)]);

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Kiosk>(`/admin/kiosks/${kiosk!.id}`, { method: "PATCH", body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["kiosks"] }),
  });

  if (!kiosk) return null;
  const changed = Object.fromEntries(
    CONFIG_FIELDS.filter((f) => config[f.key] !== "" && config[f.key] !== kiosk.config[f.key]).map((f) => [f.key, config[f.key]]),
  );
  return (
    <Drawer open onClose={onClose} title={`${kiosk.name} settings`}>
      <div className="space-y-4">
        <div>
          <label className="label" htmlFor="k-name">Name</label>
          <input id="k-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        {CONFIG_FIELDS.map((f) => (
          <div key={f.key} className="flex items-center justify-between gap-4">
            <label htmlFor={`cfg-${f.key}`} className="text-sm">
              <span className="font-medium">{f.label}</span>
              {f.hint && <span className="block text-xs text-slate-500">{f.hint}</span>}
            </label>
            {f.kind === "bool" ? (
              <input id={`cfg-${f.key}`} type="checkbox" className="h-5 w-5 accent-brand-600" checked={!!config[f.key]} onChange={(e) => setConfig({ ...config, [f.key]: e.target.checked })} />
            ) : (
              <input
                id={`cfg-${f.key}`}
                type="number"
                className="input w-32"
                min={f.min}
                max={f.max}
                step={f.step}
                value={String(config[f.key] ?? "")}
                onChange={(e) => setConfig({ ...config, [f.key]: e.target.value === "" ? "" : Number(e.target.value) })}
              />
            )}
          </div>
        ))}
        <p className="text-xs text-slate-500">Kiosks pick up changes on their next check-in (within a minute).</p>
        <ErrorBox error={save.error} />
        {save.isSuccess && <p className="text-sm text-emerald-600">Saved.</p>}
        <div className="flex flex-wrap justify-between gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
          <button
            className={kiosk.status === "DISABLED" ? "btn-secondary" : "btn-danger"}
            disabled={save.isPending || kiosk.status === "PENDING"}
            onClick={() => save.mutate({ status: kiosk.status === "DISABLED" ? "ACTIVE" : "DISABLED" })}
          >
            {kiosk.status === "DISABLED" ? "Enable kiosk" : "Disable kiosk"}
          </button>
          <button
            className="btn-primary"
            disabled={save.isPending}
            onClick={() => save.mutate({ ...(name.trim() !== kiosk.name ? { name: name.trim() } : {}), config: changed })}
          >
            Save settings
          </button>
        </div>
      </div>
    </Drawer>
  );
}
