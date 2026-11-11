import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, login as apiLogin, logout as apiLogout, refresh, setSignedOutHandler } from "./api";
import type { Me } from "./types";

type AuthState = {
  me: Me | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  can: (...perms: string[]) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const clear = useCallback(() => {
    setMe(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    setSignedOutHandler(clear);
    // Restore the session from the refresh cookie on page load.
    (async () => {
      try {
        if (await refresh()) setMe(await api<Me>("/auth/me"));
      } finally {
        setLoading(false);
      }
    })();
  }, [clear]);

  const signIn = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password);
    setMe(await api<Me>("/auth/me"));
  }, []);

  const signOut = useCallback(async () => {
    await apiLogout();
    clear();
  }, [clear]);

  const can = useCallback((...perms: string[]) => !!me && perms.every((p) => me.permissions.includes(p)), [me]);

  const value = useMemo(() => ({ me, loading, signIn, signOut, can }), [me, loading, signIn, signOut, can]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
