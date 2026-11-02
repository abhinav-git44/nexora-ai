"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, refreshToken, session } from "./api";
import type { Org, OrgSummary, User } from "./types";

type AuthState = {
  ready: boolean;
  user: User | null;
  orgs: OrgSummary[];
  org: Org | null;
  can: (perm: string) => boolean;
  hasFeature: (f: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; full_name: string; organization_name?: string; invitation_token?: string }) => Promise<void>;
  logout: () => Promise<void>;
  switchOrg: (id: string) => Promise<void>;
  reload: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [orgs, setOrgs] = useState<OrgSummary[]>([]);
  const [org, setOrg] = useState<Org | null>(null);

  const loadMe = useCallback(async () => {
    const me = await api<{ user: User; organizations: OrgSummary[] }>("/auth/me", { noOrg: true });
    setUser(me.user);
    setOrgs(me.organizations);
    let current = session.getOrg();
    if (!current || !me.organizations.some((o) => o.id === current)) current = me.organizations[0]?.id ?? null;
    session.setOrg(current);
    if (current) setOrg(await api<Org>("/orgs/current"));
    else setOrg(null);
  }, []);

  useEffect(() => {
    session.onUnauthorized(() => {
      session.setToken(null);
      setUser(null);
    });
    (async () => {
      try {
        const oauthReturn = typeof window !== "undefined" && window.location.search.includes("oauth=1");
        if ((session.hasHint() || oauthReturn) && (await refreshToken())) await loadMe();
      } catch {
        /* signed out */
      } finally {
        setReady(true);
      }
    })();
  }, [loadMe]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string }>("/auth/login", { body: { email, password }, noOrg: true });
    session.setToken(r.access_token);
    await loadMe();
  }, [loadMe]);

  const register = useCallback(async (data: Parameters<AuthState["register"]>[0]) => {
    const r = await api<{ access_token: string }>("/auth/register", { body: data, noOrg: true });
    session.setToken(r.access_token);
    session.setOrg(null);
    await loadMe();
  }, [loadMe]);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST", noOrg: true }).catch(() => undefined);
    session.setToken(null);
    setUser(null);
    setOrg(null);
    router.push("/login");
  }, [router]);

  const switchOrg = useCallback(async (id: string) => {
    session.setOrg(id);
    setOrg(await api<Org>("/orgs/current"));
    router.push("/app");
  }, [router]);

  const value = useMemo<AuthState>(() => ({
    ready, user, orgs, org, login, register, logout, switchOrg, reload: loadMe,
    can: (p) => !!org?.permissions.includes(p),
    hasFeature: (f) => !!org?.plan.features.includes(f),
  }), [ready, user, orgs, org, login, register, logout, switchOrg, loadMe]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
