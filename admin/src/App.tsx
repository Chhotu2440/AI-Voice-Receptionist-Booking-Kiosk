import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout, NAV } from "./components/Layout";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { AiUsagePage } from "./pages/AiUsage";
import { BookingsPage } from "./pages/Bookings";
import { DashboardPage } from "./pages/Dashboard";
import { EnquiriesPage } from "./pages/Enquiries";
import { KiosksPage } from "./pages/Kiosks";
import { Login } from "./pages/Login";

function Guard({ perm, children }: { perm: string; children: ReactNode }) {
  const { can } = useAuth();
  if (can(perm)) return <>{children}</>;
  return (
    <div className="card p-8 text-center">
      <h1 className="text-lg font-semibold">No access</h1>
      <p className="mt-1 text-sm text-slate-500">Your role can't open this page. Ask the owner if you need it.</p>
    </div>
  );
}

export function App() {
  const { me, loading } = useAuth();
  if (loading) return <Loading label="Starting…" />;
  if (!me) return <Login />;
  const home = NAV.find((n) => me.permissions.includes(n.perm))?.to ?? "/";
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route
          index
          element={
            me.permissions.includes("dashboard.read") ? <DashboardPage /> : <Navigate to={home} replace />
          }
        />
        <Route path="bookings" element={<Guard perm="booking.read"><BookingsPage /></Guard>} />
        <Route path="enquiries" element={<Guard perm="enquiry.manage"><EnquiriesPage /></Guard>} />
        <Route path="kiosks" element={<Guard perm="kiosk.manage"><KiosksPage /></Guard>} />
        <Route path="ai" element={<Guard perm="dashboard.read"><AiUsagePage /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
