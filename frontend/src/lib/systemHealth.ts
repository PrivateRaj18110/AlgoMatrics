// Platform health signals shared by the wallboard and the System Health page.
//
// Three sources, from most to least privileged:
//   /admin/health         platform admins: database + Redis probes with latency,
//                         outbox backlog and a heartbeat age for every background
//                         process (market data, engine, scheduler, relay, e-mail)
//   /health/dependencies  anyone: database + Redis probes (no process detail)
//   /health/info          anyone: version, build and environment
//
// As everywhere on the wallboard, a signal that did not answer is UNKNOWN —
// never a green tick by default.

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { OperationalState } from "@/lib/wallboard";
import type { OpsMachine } from "@/types/api";

export interface ServiceHeartbeat {
  name: string;
  label: string;
  age_seconds: number | null;
  stale_after_seconds: number;
}

export interface PlatformHealth {
  database: boolean;
  redis: boolean;
  outbox_backlog: number;
  market_data_age_seconds: number | null;
  engine_heartbeat_age_seconds: number | null;
  active_runs: number;
  database_latency_ms?: number | null;
  redis_latency_ms?: number | null;
  services?: ServiceHeartbeat[];
  checked_at?: string | null;
}

export interface DependencyReport {
  status: "ok" | "degraded";
  dependencies: { name: string; healthy: boolean; detail: string | null }[];
  /** Browser-measured round trip of this request, in ms. */
  round_trip_ms: number;
}

export interface BuildInfo {
  service: string;
  version: string;
  build_sha: string;
  environment: string;
}

/** Full platform health. Platform admins only; everyone else skips the call. */
export function usePlatformHealth(enabled: boolean) {
  return useQuery({
    queryKey: ["platform-health"],
    queryFn: () => api<PlatformHealth>("/admin/health"),
    enabled,
    refetchInterval: 15_000,
    retry: false,
  });
}

/** Public database/Redis probe, timed from this browser. */
export function useDependencyProbe() {
  return useQuery({
    queryKey: ["health-dependencies"],
    queryFn: async () => {
      const started = performance.now();
      const report = await api<Omit<DependencyReport, "round_trip_ms">>("/health/dependencies", {
        skipOrg: true,
      });
      return { ...report, round_trip_ms: Math.round(performance.now() - started) };
    },
    refetchInterval: 15_000,
  });
}

export function useBuildInfo() {
  return useQuery({
    queryKey: ["health-info"],
    queryFn: () => api<BuildInfo>("/health/info", { skipOrg: true }),
    staleTime: 10 * 60_000,
  });
}

/**
 * State of a background process from its heartbeat.
 *
 * The heartbeat keys expire (a couple of minutes), so a missing key means the
 * process has been silent for longer than that or never started: CRITICAL.
 */
export function heartbeatState(age: number | null | undefined, staleAfter: number): OperationalState {
  if (age === null || age === undefined || !Number.isFinite(age)) return "CRITICAL";
  if (age <= staleAfter) return "HEALTHY";
  return "STALE";
}

/** "4s", "3m 20s", "2h 5m" — for heartbeat and report ages. */
export function ageText(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  if (total < 3600) return `${Math.floor(total / 60)}m ${total % 60}s`;
  if (total < 86_400) return `${Math.floor(total / 3600)}h ${Math.floor((total % 3600) / 60)}m`;
  return `${Math.floor(total / 86_400)}d ${Math.floor((total % 86_400) / 3600)}h`;
}

/** Seconds between an ISO instant and `now`, or null when there is no instant. */
export function secondsSince(value: string | null | undefined, now: number): number | null {
  if (!value) return null;
  const at = Date.parse(value);
  return Number.isNaN(at) ? null : Math.max(0, (now - at) / 1000);
}

// Placeholder machines seeded by older agent builds. They never report and
// only clutter the selector.
const PLACEHOLDER_IDS = new Set(["mch-london", "mch-gcloud", "mch-pc"]);
const PLACEHOLDER_NAMES = new Set(["London VPS", "Personal Computer"]);
const PRIMARY_IDS = new Set(["mch-agent-google-vm-raj-quant-server"]);
const PRIMARY_NAMES = new Set(["google-vm-raj-quant-server"]);

/** Execution machines worth showing health for. */
export function reportingMachines(machines: readonly OpsMachine[] | undefined): OpsMachine[] {
  return (machines ?? []).filter(
    (machine) => Boolean(machine.id) && !PLACEHOLDER_IDS.has(machine.id) && !PLACEHOLDER_NAMES.has(machine.name),
  );
}

/** The machine to show by default: the chosen one if still present, else the primary VM, else the first. */
export function pickMachine(machines: readonly OpsMachine[], chosen: string | null | undefined): string {
  if (chosen && machines.some((machine) => machine.id === chosen)) return chosen;
  const primary = machines.find((machine) => PRIMARY_IDS.has(machine.id) || PRIMARY_NAMES.has(machine.name));
  return primary?.id ?? machines[0]?.id ?? "";
}
