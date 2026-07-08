import type { ReactNode } from "react";

import { useFeatureFlags } from "@/lib/hooks";

/** Returns whether a feature flag is enabled for the current user/org/env. */
export function useFeatureEnabled(key: string): boolean {
  const { data } = useFeatureFlags();
  return data?.[key] ?? false;
}

/**
 * Renders children only when `flag` is enabled for the current context.
 * Optionally renders `fallback` when disabled.
 */
export function Feature({
  flag,
  children,
  fallback = null,
}: {
  flag: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  return useFeatureEnabled(flag) ? <>{children}</> : <>{fallback}</>;
}
