import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => ({
  useOpsMachines: vi.fn(),
  useOpsEvents: vi.fn(),
  useOpsTrades: vi.fn(),
  useOpsStrategies: vi.fn(),
  useOpsAnalytics: vi.fn(),
  useOpsLogs: vi.fn(),
  useOpsAlerts: vi.fn(),
  useOpsOrders: vi.fn(),
  useOpsOverview: vi.fn(),
  useOpsSystemHealth: vi.fn(),
}));

vi.mock("@/lib/hooks", () => hooks);

import {
  ClosedTradesPage,
  EngineStrategiesPage,
  EventsPage,
  MachinesPage,
  OpsOverviewStrip,
  SystemHealthPage,
} from "@/pages/operations/OperationsPages";

describe("operations pages", () => {
  beforeEach(() => {
    Object.values(hooks).forEach((fn) => fn.mockReset());
  });

  it("renders empty machines without fixture hosts", () => {
    hooks.useOpsMachines.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<MachinesPage />);
    expect(screen.getByText("Awaiting telemetry")).toBeInTheDocument();
    expect(screen.queryByText("London VPS")).not.toBeInTheDocument();
    expect(screen.getByText(/Asia\/Kolkata/)).toBeInTheDocument();
  });

  it("renders closed trades empty state", () => {
    hooks.useOpsTrades.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<ClosedTradesPage />);
    expect(screen.getByText("No data available")).toBeInTheDocument();
    expect(screen.queryByText("Gold Scalper")).not.toBeInTheDocument();
  });

  it("renders events without treating them as trades", () => {
    hooks.useOpsEvents.mockReturnValue({
      data: [
        {
          id: "evt-1",
          time: "2026-08-17T12:00:00.000Z",
          received_at: "2026-08-17T12:00:01.000Z",
          event_type: "heartbeat",
          machine_id: "mch-gcp-1",
          strategy: null,
          symbol: null,
          message: "ok",
        },
      ],
      isLoading: false,
      isError: false,
    });
    render(<EventsPage />);
    expect(screen.getAllByText("heartbeat").length).toBeGreaterThan(0);
    expect(screen.getByText("Heartbeats are not trades.", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("Closed Trades")).not.toBeInTheDocument();
  });

  it("renders strategy empty copy instead of demo names", () => {
    hooks.useOpsStrategies.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(
      <MemoryRouter>
        <EngineStrategiesPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("No strategy data available")).toBeInTheDocument();
    expect(screen.queryByText("Mean Reversion FX")).not.toBeInTheDocument();
  });

  it("renders a real strategy and symbol breakdown fields", () => {
    hooks.useOpsStrategies.mockReturnValue({
      data: [
        {
          strategy_id: "mch-gcp-1::Alpha",
          strategy_name: "Alpha",
          machine_id: "mch-gcp-1",
          status: "online",
          last_heartbeat: "2026-08-17T12:00:00.000Z",
          symbols: ["NIFTY"],
          trade_count: 1,
          total_pnl: 12.5,
          win_rate: 1,
          avg_latency_ms: 8,
        },
      ],
      isLoading: false,
      isError: false,
    });
    render(
      <MemoryRouter>
        <EngineStrategiesPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("NIFTY")).toBeInTheDocument();
  });

  it("renders OpsOverviewStrip with clear historical labels", () => {
    hooks.useOpsOverview.mockReturnValue({
      data: {
        machine_count: 6,
        online_machines: 0,
        closed_trade_count: 85,
        total_pnl: 3141,
        awaiting_telemetry: false,
        telemetry_configured: true,
      },
      isLoading: false,
      isError: false,
    });
    render(<OpsOverviewStrip />);
    expect(screen.getByText("Registered machines")).toBeInTheDocument();
    expect(screen.getByText("Execution offline")).toBeInTheDocument();
    expect(screen.getByText("Recorded closed trades")).toBeInTheDocument();
    expect(screen.getByText("Historical Engine PnL")).toBeInTheDocument();
    expect(screen.getByText("85")).toBeInTheDocument();
  });

  it("renders SystemHealthPage empty state when no snapshots exist", () => {
    hooks.useOpsMachines.mockReturnValue({
      data: [
        {
          id: "mch-agent-google-vm-raj-quant-server",
          name: "google-vm-raj-quant-server",
          hostname: "google-vm-raj-quant-server",
          status: "online",
        },
      ],
      isLoading: false,
      isError: false,
    });
    hooks.useOpsSystemHealth.mockReturnValue({
      data: {
        machine_id: "mch-agent-google-vm-raj-quant-server",
        machine_name: "google-vm-raj-quant-server",
        is_live: true,
        current_execution_status: "online",
        current_health_status: null,
        last_health_timestamp: null,
        points: [],
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemHealthPage />);
    expect(screen.getByText("System Health")).toBeInTheDocument();
    expect(screen.getByText("No system health telemetry available.")).toBeInTheDocument();
    expect(screen.getByText("LIVE TELEMETRY")).toBeInTheDocument();
  });

  it("renders SystemHealthPage with real metrics and IST header", () => {
    hooks.useOpsMachines.mockReturnValue({
      data: [
        {
          id: "mch-agent-google-vm-raj-quant-server",
          name: "google-vm-raj-quant-server",
          hostname: "google-vm-raj-quant-server",
          status: "online",
        },
      ],
      isLoading: false,
      isError: false,
    });
    hooks.useOpsSystemHealth.mockReturnValue({
      data: {
        machine_id: "mch-agent-google-vm-raj-quant-server",
        machine_name: "google-vm-raj-quant-server",
        is_live: true,
        current_execution_status: "online",
        current_health_status: "STABLE",
        last_health_timestamp: "2026-08-24T10:06:07.000Z",
        points: [
          {
            id: "hlth-1",
            machine_id: "mch-agent-google-vm-raj-quant-server",
            timestamp: "2026-08-24T10:06:07.000Z",
            tick_rate: 15.0,
            tick_delay_ms: 0.2,
            queue_size: 1,
            queue_wait_ms: 2.0,
            avg_latency_ms: 6.0,
            p95_latency_ms: 8.0,
            p99_latency_ms: 9.0,
            api_success_pct: 100.0,
            signal_fill_rate_pct: 95.0,
            cpu_usage_pct: 12.0,
            memory_mb: 250.0,
            status: "STABLE",
          },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemHealthPage />);
    expect(screen.getByText("System Health")).toBeInTheDocument();
    expect(screen.getByText("CPU Usage & Memory")).toBeInTheDocument();
    expect(screen.getByText("Latency Profile")).toBeInTheDocument();
    expect(screen.getByText("Tick Rate & Tick Delay")).toBeInTheDocument();
    expect(screen.getByText("Queue Health")).toBeInTheDocument();
    expect(screen.getByText("API Reliability & Signal Fill Rate")).toBeInTheDocument();
    expect(screen.getByText("STABLE")).toBeInTheDocument();
    expect(screen.getByText("ONLINE")).toBeInTheDocument();
  });
});
