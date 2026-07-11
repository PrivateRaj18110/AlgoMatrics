import { clsx } from "clsx";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { NotificationBell } from "@/components/NotificationBell";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Badge, Button, Field, Input, Modal } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useFeatureFlags } from "@/lib/hooks";
import { liveChannel } from "@/lib/ws";
import { activeOrg, useAuth } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";
import type { Organization } from "@/types/api";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  flag?: string;
}

const NAV: NavItem[] = [
  { to: "/app/dashboard", label: "Dashboard", icon: "M3 12l9-9 9 9M5 10v10h14V10" },
  { to: "/app/strategies", label: "Strategies", icon: "M4 6h16M4 12h16M4 18h10" },
  {
    to: "/app/marketplace",
    label: "Marketplace",
    icon: "M3 9l1-4h16l1 4M4 9v11h16V9M9 13h6",
    flag: "marketplace",
  },
  { to: "/app/brokers", label: "Brokers", icon: "M3 7h18v13H3zM8 7V4h8v3" },
  { to: "/app/trading", label: "Trading", icon: "M3 3v18h18M7 14l4-4 3 3 5-6" },
  { to: "/app/market", label: "Market", icon: "M4 20V10M10 20V4M16 20v-8M22 20H2M2 4l5 3 5-5 5 4 5-2" },
  { to: "/app/watchlists", label: "Watchlists", icon: "M12 5c-5 0-9 4.5-10 7 1 2.5 5 7 10 7s9-4.5 10-7c-1-2.5-5-7-10-7zm0 3a4 4 0 110 8 4 4 0 010-8z" },
  { to: "/app/analytics", label: "Analytics", icon: "M4 20V10M10 20V4M16 20v-8M22 20H2" },
  { to: "/app/audit", label: "Audit log", icon: "M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" },
  {
    to: "/app/assistant",
    label: "Assistant",
    icon: "M12 3a5 5 0 015 5c0 2-1 3-2 4v2H9v-2c-1-1-2-2-2-4a5 5 0 015-5zM9 20h6",
    flag: "ai",
  },
  { to: "/app/subscription", label: "Subscription", icon: "M3 10h18M7 15h4M3 6h18v12H3z" },
  { to: "/app/settings", label: "Settings", icon: "M12 15a3 3 0 100-6 3 3 0 000 6z" },
];

function Icon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" className="size-4.5 shrink-0" fill="none" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" d={path} />
    </svg>
  );
}

export function AppLayout() {
  const user = useAuth((state) => state.user);
  const organizations = useAuth((state) => state.organizations);
  const activeOrgId = useAuth((state) => state.activeOrgId);
  const switchOrg = useAuth((state) => state.switchOrg);
  const setOrganizations = useAuth((state) => state.setOrganizations);
  const { data: flags } = useFeatureFlags();
  const logout = useAuth((state) => state.logout);
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [createOrgOpen, setCreateOrgOpen] = useState(false);
  const [organizationName, setOrganizationName] = useState("");
  const [creatingOrganization, setCreatingOrganization] = useState(false);
  const org = activeOrg();

  useEffect(() => {
    void liveChannel.connect();
    return () => liveChannel.close();
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // Keyboard shortcut: "g" then a key jumps between sections.
  useEffect(() => {
    let pending = false;
    const map: Record<string, string> = {
      d: "/app/dashboard",
      s: "/app/strategies",
      b: "/app/brokers",
      t: "/app/trading",
      o: "/app/trading/orders",
      p: "/app/trading/positions",
      a: "/app/analytics",
      r: "/app/trading/risk",
    };
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
        return;
      if (event.key === "g") {
        pending = true;
        window.setTimeout(() => (pending = false), 800);
        return;
      }
      if (pending && map[event.key]) {
        navigate(map[event.key]);
        pending = false;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate]);

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  async function createOrganization() {
    const name = organizationName.trim();
    if (!name) return;
    setCreatingOrganization(true);
    try {
      const created = await api<Organization>("/organizations", {
        method: "POST",
        body: { name },
        skipOrg: true,
      });
      setOrganizations([...organizations, created]);
      switchOrg(created.id);
      setOrganizationName("");
      setCreateOrgOpen(false);
      toastSuccess("Organization created");
    } catch (error) {
      toastError(
        "Could not create organization",
        error instanceof ApiError ? error.detail : undefined,
      );
    } finally {
      setCreatingOrganization(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-surface-50 text-slate-900 dark:bg-surface-950 dark:text-slate-100">
      {/* Sidebar */}
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-slate-200 bg-white transition-transform dark:border-surface-800 dark:bg-surface-900 lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-4 dark:border-surface-800">
          <div className="flex size-7 items-center justify-center rounded-md bg-accent-600 text-sm font-bold text-white">
            A
          </div>
          <span className="font-semibold">Algo Matrics</span>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {NAV.filter((item) => !item.flag || flags?.[item.flag]).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent-500/10 text-accent-600 dark:text-accent-300"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-surface-800",
                )
              }
            >
              <Icon path={item.icon} />
              {item.label}
            </NavLink>
          ))}
          {user?.is_platform_admin && (
            <NavLink
              to="/app/admin"
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-violet-500/10 text-violet-600 dark:text-violet-300"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-surface-800",
                )
              }
            >
              <Icon path="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z" />
              Admin
            </NavLink>
          )}
        </nav>
        <div className="border-t border-slate-200 p-3 text-xs text-slate-400 dark:border-surface-800">
          <p className="truncate">{user?.email}</p>
          <button
            onClick={handleLogout}
            className="mt-2 flex items-center gap-1.5 text-slate-500 hover:text-loss-500"
          >
            <Icon path="M16 17l5-5-5-5M21 12H9M12 19H5V5h7" />
            Sign out
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Main */}
      <div className="flex flex-1 flex-col lg:pl-0">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur dark:border-surface-800 dark:bg-surface-900/80">
          <div className="flex items-center gap-3">
            <button
              className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden dark:hover:bg-surface-800"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Icon path="M4 6h16M4 12h16M4 18h16" />
            </button>
            {organizations.length > 0 && (
              <select
                value={activeOrgId ?? ""}
                onChange={(event) => switchOrg(event.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-surface-700 dark:bg-surface-850"
                aria-label="Active organization"
              >
                {organizations.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.name}
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              onClick={() => setCreateOrgOpen(true)}
              className="rounded-md px-2 py-1 text-sm text-accent-600 hover:bg-accent-500/10 dark:text-accent-300"
              aria-label="Create organization"
              title="Create organization"
            >
              +
            </button>
            {org && (
              <Badge color="blue" className="hidden sm:inline-flex">
                {org.role}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {!user?.email_verified && (
              <Badge color="amber" className="hidden md:inline-flex">
                E-mail unverified
              </Badge>
            )}
            <NotificationBell />
            <ThemeToggle />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/app/settings/profile")}
              className="hidden sm:inline-flex"
            >
              {user?.full_name?.split(" ")[0] ?? "Account"}
            </Button>
          </div>
        </header>
        <main className="flex-1 overflow-x-hidden p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
      <Modal
        open={createOrgOpen}
        onClose={() => setCreateOrgOpen(false)}
        title="Create organization"
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void createOrganization();
          }}
        >
          <Field
            label="Organization name"
            hint="You will become the owner and can invite teammates afterward."
            required
          >
            <Input
              value={organizationName}
              onChange={(event) => setOrganizationName(event.target.value)}
              minLength={1}
              maxLength={200}
              autoFocus
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreateOrgOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              loading={creatingOrganization}
              disabled={!organizationName.trim()}
            >
              Create
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
