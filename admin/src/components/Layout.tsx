import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../lib/auth";

export const NAV: { to: string; label: string; perm: string; icon: string }[] = [
  { to: "/", label: "Dashboard", perm: "dashboard.read", icon: "M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" },
  { to: "/bookings", label: "Bookings", perm: "booking.read", icon: "M7 2v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2H7zm-2 8h14v10H5V10z" },
  { to: "/enquiries", label: "Event enquiries", perm: "enquiry.manage", icon: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z" },
  { to: "/customers", label: "Customers", perm: "customer.read", icon: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0 2c-4 0-8 2-8 5v1h16v-1c0-3-4-5-8-5z" },
  { to: "/kiosks", label: "Kiosks", perm: "kiosk.manage", icon: "M4 3h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-6v2h3v2H7v-2h3v-2H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm1 2v9h14V5H5z" },
  { to: "/users", label: "Staff accounts", perm: "user.manage", icon: "M16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm0 2c-2.7 0-8 1.3-8 4v2h10v-2c0-1 .4-1.9 1.1-2.7C10 13.4 8.8 13 8 13zm8 0c-.3 0-.7 0-1.1.1A4.5 4.5 0 0 1 17 17v2h7v-2c0-2.7-5.3-4-8-4z" },
  { to: "/audit", label: "Audit log", perm: "audit.read", icon: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 7V3.5L18.5 9H13zM8 13h8v2H8v-2zm0 4h8v2H8v-2z" },
  { to: "/ai", label: "AI & voice cost", perm: "dashboard.read", icon: "M12 2a4 4 0 0 1 4 4v5a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4zm-7 9h2a5 5 0 0 0 10 0h2a7 7 0 0 1-6 6.92V21h-2v-3.08A7 7 0 0 1 5 11z" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0 fill-current" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  return (
    <button
      className="btn-secondary !px-2.5"
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => {
        const next = !dark;
        document.documentElement.classList.toggle("dark", next);
        try {
          localStorage.setItem("plt-admin-theme", next ? "dark" : "light");
        } catch {
          /* storage blocked: theme still switches for this page */
        }
        setDark(next);
      }}
    >
      {dark ? "☀" : "☾"}
    </button>
  );
}

export function Layout() {
  const { me, signOut, can } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const items = NAV.filter((n) => can(n.perm));

  const nav = (
    <nav className="flex flex-col gap-1 p-3">
      {items.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/"}
          onClick={() => setMenuOpen(false)}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
              isActive
                ? "bg-brand-600 text-white"
                : "text-slate-300 hover:bg-slate-800 hover:text-white"
            }`
          }
        >
          <Icon d={n.icon} />
          {n.label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen lg:pl-60">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col bg-slate-900 lg:flex">
        <Brand />
        {nav}
      </aside>
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMenuOpen(false)} />
          <aside className="relative h-full w-64 bg-slate-900">
            <Brand />
            {nav}
          </aside>
        </div>
      )}
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80 lg:px-8">
        <button className="btn-secondary !px-2.5 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
          ☰
        </button>
        <div className="flex-1" />
        <ThemeToggle />
        <div className="hidden text-right text-sm sm:block">
          <div className="font-medium" data-testid="user-name">
            {me?.name}
          </div>
          <div className="text-xs text-slate-500">{me?.role_codes.join(", ")}</div>
        </div>
        <button className="btn-secondary" onClick={() => void signOut()}>
          Sign out
        </button>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex h-14 items-center gap-2.5 border-b border-slate-800 px-5">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-sm font-bold text-white">PL</span>
      <div className="leading-tight">
        <div className="text-sm font-semibold text-white">Play Laser Tag</div>
        <div className="text-xs text-slate-400">Admin</div>
      </div>
    </div>
  );
}
