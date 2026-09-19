import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { Spinner } from "@/components/ui";
import { useAuth } from "@/stores/auth";

const BOOT_LINES = [
  ["DATA", "CONNECTED"],
  ["STRATEGIES", "READY"],
  ["RISK", "READY"],
  ["EXECUTION", "READY"],
];

export function SessionLoading({ label = "INITIALIZING QUANT ENGINE..." }: { label?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-surface-950 px-6 text-slate-300">
      <p className="text-sm font-semibold tracking-[0.32em] text-white">ALGOMATRIC</p>
      <p className="mt-6 font-mono text-[11px] tracking-[0.22em] text-accent-400">{label}</p>
      <ul className="mt-8 w-full max-w-xs space-y-2 font-mono text-[11px] tracking-wide text-slate-500">
        {BOOT_LINES.map(([key, value]) => (
          <li key={key} className="flex justify-between border-b border-white/6 pb-1">
            <span>{key}</span>
            <span className="text-profit-400">{value}</span>
          </li>
        ))}
      </ul>
      <Spinner className="mt-8 size-5 text-accent-500" />
    </div>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuth((state) => state.status);
  const location = useLocation();
  if (status === "booting") {
    return <SessionLoading />;
  }
  if (status !== "authenticated") {
    const returnTo = `${location.pathname}${location.search}`;
    return <Navigate to="/login" replace state={{ returnTo }} />;
  }
  return <>{children}</>;
}

export function RequireAnonymous({ children }: { children: ReactNode }) {
  const status = useAuth((state) => state.status);
  if (status === "booting") {
    return <SessionLoading />;
  }
  if (status === "authenticated") {
    return <Navigate to="/app/dashboard" replace />;
  }
  return <>{children}</>;
}

export function RootRedirect() {
  const status = useAuth((state) => state.status);
  if (status === "booting") {
    return <SessionLoading />;
  }
  if (status === "authenticated") {
    return <Navigate to="/app/dashboard" replace />;
  }
  return <Navigate to="/login" replace />;
}

export function OpsRedirect() {
  const status = useAuth((state) => state.status);
  if (status === "booting") {
    return <SessionLoading />;
  }
  if (status === "authenticated") {
    return <Navigate to="/app/dashboard" replace />;
  }
  return <Navigate to="/login" replace />;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const user = useAuth((state) => state.user);
  if (!user?.is_platform_admin) {
    return <Navigate to="/app/dashboard" replace />;
  }
  return <>{children}</>;
}
