import { clsx } from "clsx";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { BrandMark } from "@/components/BrandMark";
import { Seo } from "@/components/Seo";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Badge, Button, Field, Input, Modal } from "@/components/ui";
import { Glyph } from "@/components/icons";
import { ApiError, MFA_REQUIRED_EVENT, api } from "@/lib/api";
import { useSecurityOverview } from "@/lib/hooks";
import { INTERNATIONAL_MARKET_ENABLED } from "@/lib/marketRegion";
import { liveChannel } from "@/lib/ws";
import { activeOrg, useAuth } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";
import type { Organization } from "@/types/api";

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

interface MarketLeaf {
  segment: string;
  label: string;
}

const MARKET_LEAVES: MarketLeaf[] = [
  { segment: "overview", label: "Overview" },
  { segment: "strategies", label: "Strategies" },
  { segment: "positions", label: "Positions" },
  { segment: "closed-trades", label: "Closed Trades" },
  { segment: "portfolio", label: "Portfolio" },
  { segment: "brokers", label: "Brokers" },
  { segment: "analytics", label: "Analytics" },
  { segment: "risk", label: "Risk" },
  { segment: "execution", label: "Execution" },
  { segment: "logs", label: "Logs" },
  { segment: "system-health", label: "System Health" },
];

const DASHBOARD_NAV: NavItem = {
  to: "/app/dashboard",
  label: "Dashboard",
  icon: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
};

// Sections are presentation only. The DOM order of the links inside them is
// the same as the old flat list (AppLayout.test.tsx pins parts of it).
const WORKSPACE_NAV: NavItem[] = [
  { to: "/app/todo", label: "To Do List", icon: "M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" },
  { to: "/app/calendar", label: "Calendar", icon: "M8 3v3M16 3v3M4 9h16M5 5h14a1 1 0 011 1v14a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z" },
  {
    to: "/app/personal-health",
    label: "Personal Health",
    icon: "M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z",
  },
];

const MARKETS_NAV: NavItem[] = [
  { to: "/app/market-update", label: "Market Update", icon: "M4 20V10M10 20V4M16 20v-8M22 20H2" },
  {
    to: "/app/pre-market",
    label: "Pre-market",
    icon: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 2",
  },
  {
    to: "/app/heatmap",
    label: "Heatmap",
    icon: "M4 4h4v4H4zM10 4h4v4h-4zM16 4h4v4h-4zM4 10h4v4H4zM10 10h4v4h-4zM16 10h4v4h-4zM4 16h4v4H4zM10 16h4v4h-4zM16 16h4v4h-4z",
  },
  {
    to: "/app/market-intelligence",
    label: "Market Intelligence",
    icon: "M12 3a9 9 0 100 18 9 9 0 000-18zm0 4a5 5 0 100 10 5 5 0 000-10zm0 4a1 1 0 100 2 1 1 0 000-2z",
  },
];

const OPERATIONS_NAV: NavItem[] = [
  { to: "/app/audit-log", label: "Audit Log", icon: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h6M9 16h6" },
  { to: "/app/system-health", label: "System Health", icon: "M22 12h-4l-3 9L9 3l-3 9H2" },
  // Full-screen operations wallboard. Routed outside AppLayout on purpose, so
  // following this entry leaves the sidebar behind; the page carries its own
  // EXIT control back to the dashboard.
  { to: "/app/wallboard", label: "Wallboard", icon: "M3 4h18v12H3zM8 20h8M12 16v4" },
  // monitoring.v1 from the LLS Monitoring Backend. Separate entry from
  // System Health, which shows the Raj agent telemetry — two independent
  // sources, and merging them in the sidebar would imply they agree.
  {
    to: "/app/lls-monitoring",
    label: "LLS Monitoring",
    icon: "M3 12h4l3 8 4-16 3 8h4",
  },
  // Trading machines reporting over /api/v1/ingest (heartbeats, trades, logs, alerts).
  { to: "/app/devices", label: "Devices", icon: "M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01" },
];

const SETTINGS_NAV: NavItem = {
  to: "/app/settings",
  label: "Settings",
  icon: "M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4",
};

function navClass(isActive: boolean): string {
  return clsx(
    "group relative flex items-center gap-3 rounded-lg px-2.5 py-[7px] text-[13px] font-medium transition-colors",
    isActive
      ? "bg-gradient-to-r from-accent-500/[0.13] to-accent-500/[0.03] text-accent-700 before:absolute before:inset-y-1.5 before:-left-3 before:w-[3px] before:rounded-r-full before:bg-accent-500 dark:text-white dark:before:bg-accent-400"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.04] dark:hover:text-slate-100",
  );
}

function NavSection({ label, children }: { label?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      {label && (
        <p className="px-2.5 pt-5 pb-1.5 text-[10px] font-semibold tracking-[0.16em] text-slate-400 uppercase dark:text-slate-500">
          {label}
        </p>
      )}
      {children}
    </div>
  );
}

function NavItemLink({ item, end }: { item: NavItem; end?: boolean }) {
  return (
    <NavLink to={item.to} end={end} className={({ isActive }) => navClass(isActive)}>
      <Icon path={item.icon} />
      {item.label}
    </NavLink>
  );
}

function MarketGroup({
  label,
  root,
  open,
  onToggle,
  activePath,
  icon,
}: {
  label: string;
  root: string;
  open: boolean;
  onToggle: () => void;
  activePath: string;
  icon: string;
}) {
  const inside = activePath.startsWith(root);
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className={clsx(
          "group flex w-full items-center gap-3 rounded-lg px-2.5 py-[7px] text-[13px] font-medium transition-colors",
          inside
            ? "text-slate-900 dark:text-white"
            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.04] dark:hover:text-slate-100",
        )}
        aria-expanded={open}
      >
        <Icon path={icon} />
        <span className="flex-1 text-left">{label}</span>
        <svg
          viewBox="0 0 24 24"
          className={clsx("size-3.5 text-slate-400 transition-transform", open && "rotate-90")}
          fill="none"
          stroke="currentColor"
          aria-hidden
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 6l6 6-6 6" />
        </svg>
      </button>
      {open && (
        <div className="mt-0.5 ml-[18px] space-y-0.5 border-l border-slate-200 pl-3 dark:border-white/[0.07]">
          {MARKET_LEAVES.map((leaf) => {
            const to = `${root}/${leaf.segment}`;
            const active = activePath === to || activePath.startsWith(`${to}/`);
            return (
              <NavLink
                key={to}
                to={to}
                className={clsx(
                  "block rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
                  active
                    ? "bg-accent-500/10 font-medium text-accent-700 dark:text-accent-300"
                    : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.04] dark:hover:text-slate-100",
                )}
              >
                {leaf.label}
              </NavLink>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Icon({ path }: { path: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-[18px] shrink-0 text-slate-400 transition-colors group-hover:text-current group-aria-[current=page]:text-accent-600 dark:text-slate-500 dark:group-aria-[current=page]:text-accent-400"
      fill="none"
      stroke="currentColor"
      aria-hidden
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" d={path} />
    </svg>
  );
}

function initials(name: string | undefined, email: string | undefined): string {
  const source = name?.trim() || email?.split("@")[0] || "?";
  const parts = source.split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : source.slice(0, 2);
  return letters.toUpperCase();
}

function Avatar({ label, className }: { label: string; className?: string }) {
  return (
    <span
      className={clsx(
        "flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent-400 to-indigo-500 font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.3)]",
        className,
      )}
      aria-hidden
    >
      {label}
    </span>
  );
}

export function AppLayout() {
  const user = useAuth((state) => state.user);
  const organizations = useAuth((state) => state.organizations);
  const activeOrgId = useAuth((state) => state.activeOrgId);
  const switchOrg = useAuth((state) => state.switchOrg);
  const setOrganizations = useAuth((state) => state.setOrganizations);
  const logout = useAuth((state) => state.logout);
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [indiaOpen, setIndiaOpen] = useState(location.pathname.startsWith("/app/india"));
  const [internationalOpen, setInternationalOpen] = useState(
    INTERNATIONAL_MARKET_ENABLED && location.pathname.startsWith("/app/international"),
  );
  const [createOrgOpen, setCreateOrgOpen] = useState(false);
  const [organizationName, setOrganizationName] = useState("");
  const [creatingOrganization, setCreatingOrganization] = useState(false);
  const org = activeOrg();
  const userInitials = initials(user?.full_name, user?.email);
  const [mfaNotice, setMfaNotice] = useState<{ path: string; detail: string } | null>(null);
  // Platform admins see waiting access requests from anywhere in the console.
  const security = useSecurityOverview(Boolean(user?.is_platform_admin));
  const pendingApprovals = security.data?.counts.users_pending ?? 0;

  useEffect(() => {
    const onMfaRequired = (event: Event) =>
      setMfaNotice({
        path: window.location.pathname,
        detail:
          (event as CustomEvent<string>).detail ||
          "Turn on two-factor authentication to use administrator features.",
      });
    window.addEventListener(MFA_REQUIRED_EVENT, onMfaRequired);
    return () => window.removeEventListener(MFA_REQUIRED_EVENT, onMfaRequired);
  }, []);

  useEffect(() => {
    void liveChannel.connect();
    return () => liveChannel.close();
  }, []);

  useEffect(() => {
    setMobileOpen(false);
    if (location.pathname.startsWith("/app/india")) setIndiaOpen(true);
    if (INTERNATIONAL_MARKET_ENABLED && location.pathname.startsWith("/app/international")) {
      setInternationalOpen(true);
    }
  }, [location.pathname]);

  // Keyboard shortcut: "g" then a key jumps between sections.
  useEffect(() => {
    let pending = false;
    const map: Record<string, string> = {
      d: "/app/dashboard",
      s: "/app/strategies",
      b: "/app/settings/brokers",
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
    <div className="am-app-bg flex min-h-screen text-slate-900 dark:text-slate-100">
      <Seo title="ALGOMATRIC Console" noindex />
      {/* Sidebar — sticky on desktop so navigation never scrolls away with a long page. */}
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200/80 bg-white/95 backdrop-blur-xl transition-transform duration-300 dark:border-white/[0.06] dark:bg-[#0c1119]/95 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0",
          mobileOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center justify-between px-5">
          <BrandMark to="/app/dashboard" className="text-slate-900 dark:text-slate-100" />
          <button
            type="button"
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 lg:hidden dark:hover:bg-white/[0.06] dark:hover:text-slate-200"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" aria-hidden>
              <path strokeLinecap="round" strokeWidth="2" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        <div className="am-hairline mx-5 h-px opacity-60" />
        <nav className="flex-1 overflow-y-auto px-3 pt-3 pb-4">
          <NavSection>
            <NavItemLink item={DASHBOARD_NAV} end />
          </NavSection>
          <NavSection label="Workspace">
            {WORKSPACE_NAV.map((item) => (
              <NavItemLink key={item.to} item={item} />
            ))}
          </NavSection>
          <NavSection label="Markets">
            <MarketGroup
              label="India"
              root="/app/india"
              icon="M3 3v18h18M7 15l4-4 3 3 6-7"
              open={indiaOpen}
              onToggle={() => setIndiaOpen((value) => !value)}
              activePath={location.pathname}
            />
            {INTERNATIONAL_MARKET_ENABLED && (
              <MarketGroup
                label="International"
                root="/app/international"
                icon="M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z"
                open={internationalOpen}
                onToggle={() => setInternationalOpen((value) => !value)}
                activePath={location.pathname}
              />
            )}
            {MARKETS_NAV.map((item) => (
              <NavItemLink key={item.to} item={item} />
            ))}
          </NavSection>
          <NavSection label="Operations">
            {OPERATIONS_NAV.map((item) => (
              <NavItemLink key={item.to} item={item} />
            ))}
          </NavSection>
          <NavSection label="System">
            <NavItemLink item={SETTINGS_NAV} />
            {user?.is_platform_admin && (
              <NavLink to="/app/admin/security" className={({ isActive }) => navClass(isActive)}>
                <Icon path="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7zM9 12l2 2 4-4" />
                <span className="flex-1">Security</span>
                {pendingApprovals > 0 && (
                  <span
                    className="rounded-full bg-amber-500/15 px-1.5 text-[11px] font-semibold text-amber-700 tabular-nums ring-1 ring-amber-500/30 ring-inset dark:text-amber-300"
                    title={`${pendingApprovals} access request(s) waiting for approval`}
                  >
                    {pendingApprovals}
                  </span>
                )}
              </NavLink>
            )}
            {user?.is_platform_admin && (
              <NavLink
                to="/app/admin"
                className={() =>
                  clsx(
                    "group relative flex items-center gap-3 rounded-lg px-2.5 py-[7px] text-[13px] font-medium transition-colors",
                    // Security has its own entry above; every other admin tab lights this one.
                    location.pathname.startsWith("/app/admin") &&
                      !location.pathname.startsWith("/app/admin/security")
                      ? "bg-violet-500/10 text-violet-700 dark:text-violet-200"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.04] dark:hover:text-slate-100",
                  )
                }
              >
                <Icon path="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z" />
                Admin
              </NavLink>
            )}
          </NavSection>
        </nav>
        <div className="border-t border-slate-200/80 p-3 dark:border-white/[0.06]">
          <div className="flex items-center gap-3 rounded-xl px-2 py-2">
            <Avatar label={userInitials} className="size-9 text-xs" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-slate-800 dark:text-slate-100">
                {user?.full_name || "Signed in"}
              </p>
              <p className="truncate text-[11px] text-slate-500">{user?.email}</p>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-loss-500/10 hover:text-loss-500"
              aria-label="Sign out"
              title="Sign out"
            >
              <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" aria-hidden>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                  d="M16 17l5-5-5-5M21 12H9M12 19H5V5h7"
                />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-950/50 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-slate-200/70 bg-white/70 px-4 backdrop-blur-xl sm:px-6 dark:border-white/[0.06] dark:bg-surface-950/60">
          <div className="flex min-w-0 items-center gap-2">
            <button
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden dark:hover:bg-white/[0.06]"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeWidth="1.8" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            {organizations.length > 0 && (
              <div className="relative flex min-w-0 items-center">
                <svg
                  viewBox="0 0 24 24"
                  className="pointer-events-none absolute left-2.5 size-4 text-slate-400"
                  fill="none"
                  stroke="currentColor"
                  aria-hidden
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.6"
                    d="M4 21V5a1 1 0 011-1h9a1 1 0 011 1v16M15 9h4a1 1 0 011 1v11M8 8h3M8 12h3M8 16h3M3 21h18"
                  />
                </svg>
                <select
                  value={activeOrgId ?? ""}
                  onChange={(event) => switchOrg(event.target.value)}
                  className="h-9 max-w-[14rem] min-w-0 cursor-pointer appearance-none truncate rounded-lg border border-slate-200 bg-white/80 pr-8 pl-8 text-sm font-medium text-slate-800 transition-colors hover:border-slate-300 focus:border-accent-500 focus:ring-4 focus:ring-accent-500/15 focus:outline-none dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-100 dark:hover:border-white/20 [&>option]:bg-white dark:[&>option]:bg-surface-900"
                  aria-label="Active organization"
                >
                  {organizations.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.name}
                    </option>
                  ))}
                </select>
                <svg
                  viewBox="0 0 24 24"
                  className="pointer-events-none absolute right-2.5 size-3.5 text-slate-400"
                  fill="none"
                  stroke="currentColor"
                  aria-hidden
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 10l5 5 5-5" />
                </svg>
              </div>
            )}
            <button
              type="button"
              onClick={() => setCreateOrgOpen(true)}
              className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-dashed border-slate-300 text-slate-500 transition-colors hover:border-accent-500 hover:bg-accent-500/5 hover:text-accent-600 dark:border-white/15 dark:text-slate-400 dark:hover:border-accent-400 dark:hover:text-accent-300"
              aria-label="Create organization"
              title="Create organization"
            >
              <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeWidth="2" d="M12 5v14M5 12h14" />
              </svg>
            </button>
            {/* Visibility lives on a wrapper: Badge's own inline-flex beats a
                `hidden` passed through className, so the badge never hid. */}
            {org && (
              <span className="hidden sm:inline-flex">
                <Badge color="blue" className="capitalize">
                  {org.role}
                </Badge>
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {!user?.email_verified && (
              <span className="mr-1 hidden md:inline-flex">
                <Badge color="amber" dot>
                  E-mail unverified
                </Badge>
              </span>
            )}
            <NotificationBell />
            <ThemeToggle />
            <span className="mx-1.5 hidden h-6 w-px bg-slate-200 sm:block dark:bg-white/10" aria-hidden />
            <button
              type="button"
              onClick={() => navigate("/app/settings/profile")}
              className="hidden items-center gap-2 rounded-full py-1 pr-3 pl-1 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 sm:inline-flex dark:text-slate-200 dark:hover:bg-white/[0.06]"
              title="Profile"
            >
              <Avatar label={userInitials} className="size-7 text-[10px]" />
              {user?.full_name?.split(" ")[0] ?? "Account"}
            </button>
          </div>
        </header>
        <main className="flex-1 overflow-x-hidden px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-[1400px]">
            {mfaNotice && mfaNotice.path === location.pathname && (
              <div
                role="alert"
                className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/[0.08] px-4 py-3 text-sm"
              >
                <span className="flex size-8 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-300">
                  <Glyph name="shield" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-amber-900 dark:text-amber-100">
                    Two-factor authentication required
                  </p>
                  <p className="text-xs text-amber-800/80 dark:text-amber-200/70">{mfaNotice.detail}</p>
                </div>
                <Link
                  to="/app/settings/security"
                  className="rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-surface-950 hover:bg-amber-400"
                >
                  Set up 2FA
                </Link>
                <button
                  type="button"
                  onClick={() => setMfaNotice(null)}
                  className="rounded-md p-1.5 text-amber-700 hover:bg-amber-500/10 dark:text-amber-300"
                  aria-label="Dismiss"
                >
                  <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor" aria-hidden>
                    <path strokeLinecap="round" strokeWidth="2" d="M6 6l12 12M18 6L6 18" />
                  </svg>
                </button>
              </div>
            )}
            <Outlet />
          </div>
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
