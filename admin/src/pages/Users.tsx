import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, Empty, ErrorBox, Loading, Modal, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime } from "../lib/format";
import type { Page, StaffUser } from "../lib/types";

export const ROLES: { code: string; label: string; help: string }[] = [
  { code: "OWNER", label: "Owner", help: "Everything, including staff accounts, AI budget and business settings" },
  { code: "MANAGER", label: "Manager", help: "Bookings, catalogue, pricing, schedule, kiosks, customers, reports" },
  { code: "STAFF", label: "Front desk", help: "Bookings, customer look-up, enquiries" },
  { code: "VIEWER", label: "Viewer", help: "Read-only dashboard and bookings" },
];
const ROLE_LABEL = Object.fromEntries(ROLES.map((r) => [r.code, r.label]));

export function UsersPage() {
  const { me } = useAuth();
  const list = useQuery({ queryKey: ["users"], queryFn: () => api<Page<StaffUser>>("/admin/users?page_size=100") });
  const [editing, setEditing] = useState<StaffUser | "new" | null>(null);

  return (
    <>
      <PageHeader
        title="Staff accounts"
        subtitle="Who can sign in to this dashboard, and what each person can do."
        actions={<button className="btn-primary" onClick={() => setEditing("new")} data-testid="add-user">+ Add staff</button>}
      />
      <div className="card overflow-hidden">
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <div className="p-4"><ErrorBox error={list.error} /></div>
        ) : list.data.items.length === 0 ? (
          <Empty>No users.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/60">
                <tr>
                  <th className="th">Name</th>
                  <th className="th">Role</th>
                  <th className="th">Last sign-in</th>
                  <th className="th">Status</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {list.data.items.map((u) => (
                  <tr key={u.id} data-testid={`user-row-${u.email}`}>
                    <td className="td">
                      <div className="font-medium">{u.name}{u.id === me?.id && <span className="ml-2 text-xs text-slate-500">(you)</span>}</div>
                      <div className="text-xs text-slate-500">{u.email}</div>
                    </td>
                    <td className="td text-sm">{u.role_codes.map((r) => ROLE_LABEL[r] ?? r).join(", ")}</td>
                    <td className="td text-sm">{dateTime(u.last_login_at)}</td>
                    <td className="td">{u.is_active ? <Badge status="ACTIVE" /> : <Badge status="DISABLED" label="Deactivated" />}</td>
                    <td className="td text-right">
                      <button className="btn-secondary" onClick={() => setEditing(u)}>Edit</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {editing && <UserModal user={editing === "new" ? null : editing} self={editing !== "new" && editing.id === me?.id} onClose={() => setEditing(null)} />}
    </>
  );
}

function UserModal({ user, self, onClose }: { user: StaffUser | null; self: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [role, setRole] = useState(user?.role_codes[0] ?? "STAFF");
  const [password, setPassword] = useState("");
  const [active, setActive] = useState(user?.is_active ?? true);

  const m = useMutation({
    mutationFn: () => {
      if (!user) {
        return api<StaffUser>("/admin/users", {
          method: "POST",
          body: { name: name.trim(), email: email.trim(), password, roles: [role] },
        });
      }
      const body: Record<string, unknown> = {};
      if (name.trim() !== user.name) body.name = name.trim();
      if (role !== user.role_codes[0] || user.role_codes.length !== 1) body.roles = [role];
      if (active !== user.is_active) body.is_active = active;
      if (password) body.password = password;
      return api<StaffUser>(`/admin/users/${user.id}`, { method: "PATCH", body });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title={user ? `Edit ${user.name}` : "Add staff account"}>
      <div className="space-y-3 text-sm">
        <div>
          <label className="label" htmlFor="u-name">Name</label>
          <input id="u-name" autoFocus className="input" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        {!user && (
          <div>
            <label className="label" htmlFor="u-email">Email (used to sign in)</label>
            <input id="u-email" type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
        )}
        <fieldset>
          <legend className="label">Role</legend>
          <div className="space-y-1.5">
            {ROLES.map((r) => (
              <label key={r.code} className={`flex cursor-pointer gap-2 rounded-lg border p-2 ${role === r.code ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20" : "border-slate-200 dark:border-slate-700"} ${self && r.code !== "OWNER" ? "opacity-50" : ""}`}>
                <input type="radio" name="role" className="mt-0.5 accent-brand-600" checked={role === r.code} disabled={self && r.code !== "OWNER"} onChange={() => setRole(r.code)} />
                <span><span className="font-medium">{r.label}</span><span className="block text-xs text-slate-500">{r.help}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
        <div>
          <label className="label" htmlFor="u-password">{user ? "New password (leave blank to keep)" : "Temporary password"}</label>
          <input id="u-password" type="password" autoComplete="new-password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="mt-1 text-xs text-slate-500">At least 12 characters. Changing it signs the person out everywhere.</p>
        </div>
        {user && !self && (
          <label className="flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Account active (unticking signs them out immediately)
          </label>
        )}
        <ErrorBox error={m.error} />
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button
          className="btn-primary"
          disabled={m.isPending || !name.trim() || (!user && (!email.trim() || password.length < 12)) || (!!password && password.length < 12)}
          onClick={() => m.mutate()}
          data-testid="save-user"
        >
          {user ? "Save" : "Create account"}
        </button>
      </div>
    </Modal>
  );
}
