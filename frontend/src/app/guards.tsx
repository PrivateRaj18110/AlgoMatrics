import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { Spinner } from "@/components/ui";
import { useAuth } from "@/stores/auth";

export function SessionLoading({ label = "Checking session..." }: { label?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-surface-950 text-slate-300">
      <Spinner className="size-8 text-accent-500" />
      <p className="text-sm">{label}</p>
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
