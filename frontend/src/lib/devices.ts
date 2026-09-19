// Trading devices that report to the console over /api/v1/ingest.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuth } from "@/stores/auth";

export type DeviceStatus = "online" | "offline" | "never_seen" | "revoked";
export type DeviceKind = "trading" | "vps" | "mt5" | "desktop" | "other";

export interface DeviceHealth {
  cpu?: number;
  ram?: number;
  disk?: number;
  latency_ms?: number;
  version?: string;
  [metric: string]: number | string | undefined;
}

export interface DevicePosition {
  symbol: string;
  qty: number;
  avg_price?: number;
  ltp?: number;
  pnl?: number;
}

export interface Device {
  id: string;
  name: string;
  kind: DeviceKind;
  key_prefix: string;
  status: DeviceStatus;
  created_at: string;
  revoked_at: string | null;
  last_seen_at: string | null;
  last_heartbeat_at: string | null;
  last_ip: string | null;
  health: DeviceHealth | null;
  positions: DevicePosition[] | null;
  positions_at: string | null;
}

export interface CreatedDevice {
  device: Device;
  key: string;
  ingest_url: string;
}

export interface DeviceEvent {
  id: string;
  kind: "trade" | "positions" | "log" | "alert";
  severity: "debug" | "info" | "warning" | "error" | "critical";
  message: string;
  payload: Record<string, unknown>;
  occurred_at: string;
  received_at: string;
}

function orgKey(): string | null {
  return useAuth.getState().activeOrgId;
}

export function useDevices() {
  const activeOrgId = useAuth((state) => state.activeOrgId);
  return useQuery({
    queryKey: ["devices", activeOrgId],
    queryFn: () => api<Device[]>("/devices"),
    enabled: Boolean(activeOrgId),
    refetchInterval: 15_000,
  });
}

export function useDeviceEvents(deviceId: string | null, kind: DeviceEvent["kind"] | null) {
  return useQuery({
    queryKey: ["device-events", orgKey(), deviceId, kind],
    queryFn: () =>
      api<DeviceEvent[]>(`/devices/${deviceId}/events`, {
        query: { kind: kind ?? undefined, limit: 200 },
      }),
    enabled: Boolean(deviceId),
    refetchInterval: 15_000,
  });
}

export function useCreateDevice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; kind: DeviceKind }) =>
      api<CreatedDevice>("/devices", { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["devices"] }),
  });
}

export function useRevokeDevice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<Device>(`/devices/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["devices"] }),
  });
}

/** The exact request a device should send, ready to paste. */
export function curlSnippet(url: string, key: string): string {
  return [
    `curl -sS ${url} \\`,
    `  -H "X-Device-Key: ${key}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"events":[{"type":"heartbeat","cpu":23,"ram":61,"disk":48}]}'`,
  ].join("\n");
}
