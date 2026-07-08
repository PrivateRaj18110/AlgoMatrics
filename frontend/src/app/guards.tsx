import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useAuth } from "@/stores/auth";

export function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuth((state) => state.status);
  const location = useLocation();
  if (status !== "authenticated") {
    const returnTo = `${location.pathname}${location.search}`;
    return <Navigate to="/login" replace state={{ returnTo }} />;
  }
  return <>{children}</>;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const user = useAuth((state) => state.user);
  if (!user?.is_platform_admin) {
    return <Navigate to="/app/dashboard" replace />;
  }
  return <>{children}</>;
}
