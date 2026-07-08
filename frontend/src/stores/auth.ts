import { create } from "zustand";

import { api, connectAuthBridge, refreshTokens } from "@/lib/api";
import type { Organization, Tokens, UserProfile } from "@/types/api";

interface AuthState {
  user: UserProfile | null;
  accessToken: string | null;
  organizations: Organization[];
  activeOrgId: string | null;
  status: "booting" | "authenticated" | "anonymous";
  setTokens: (tokens: Tokens) => void;
  setUser: (user: UserProfile) => void;
  setOrganizations: (orgs: Organization[]) => void;
  switchOrg: (orgId: string) => void;
  bootstrap: () => Promise<void>;
  loadContext: () => Promise<void>;
  logout: () => Promise<void>;
  reset: () => void;
}

const ORG_STORAGE_KEY = "am-active-org";

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  organizations: [],
  activeOrgId: null,
  status: "booting",

  setTokens: (tokens) =>
    set({ accessToken: tokens.access_token, user: tokens.user, status: "authenticated" }),

  setUser: (user) => set({ user }),

  setOrganizations: (orgs) => {
    const stored = localStorage.getItem(ORG_STORAGE_KEY);
    const active =
      orgs.find((candidate) => candidate.id === stored)?.id ?? orgs[0]?.id ?? null;
    set({ organizations: orgs, activeOrgId: active });
    if (active) localStorage.setItem(ORG_STORAGE_KEY, active);
  },

  switchOrg: (orgId) => {
    localStorage.setItem(ORG_STORAGE_KEY, orgId);
    set({ activeOrgId: orgId });
  },

  bootstrap: async () => {
    const refreshed = await refreshTokens();
    if (!refreshed) {
      set({ status: "anonymous" });
      return;
    }
    await get().loadContext();
  },

  loadContext: async () => {
    try {
      const [user, orgs] = await Promise.all([
        api<UserProfile>("/me", { skipOrg: true }),
        api<Organization[]>("/organizations", { skipOrg: true }),
      ]);
      get().setOrganizations(orgs);
      set({ user, status: "authenticated" });
    } catch {
      set({ status: "anonymous" });
    }
  },

  logout: async () => {
    try {
      await api("/auth/logout", { method: "POST", skipOrg: true });
    } catch {
      // best effort; local state clears regardless
    }
    get().reset();
  },

  reset: () =>
    set({
      user: null,
      accessToken: null,
      organizations: [],
      activeOrgId: null,
      status: "anonymous",
    }),
}));

connectAuthBridge({
  getAccessToken: () => useAuth.getState().accessToken,
  getOrgId: () => useAuth.getState().activeOrgId,
  onTokens: (tokens) => useAuth.getState().setTokens(tokens),
  onAuthLost: () => useAuth.getState().reset(),
});

export function activeOrg(): Organization | null {
  const { organizations, activeOrgId } = useAuth.getState();
  return organizations.find((org) => org.id === activeOrgId) ?? null;
}
