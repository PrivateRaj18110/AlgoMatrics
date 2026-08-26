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
        is_live: false,
        current_execution_status: "offline",
        current_health_status: null,
        last_health_timestamp: null,
        points: [],
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemHealthPage />);
    expect(screen.getByText("System Health")).toBeInTheDocument();
    expect(
      screen.getByText("Live execution infrastructure and strategy health"),
    ).toBeInTheDocument();
    expect(screen.getByText("No system health telemetry yet.")).toBeInTheDocument();
    expect(
      screen.getByText(/The execution VM has not submitted a system_health snapshot/),
    ).toBeInTheDocument();
  });

  it("renders SystemHealthPage with 11 metric summary cards, 5 charts, and 6 time ranges", () => {
    hooks.useOpsMachines.mockReturnValue({
      data: [
        {
          id: "mch-agent-google-vm-raj-quant-server",
          name: "google-vm-raj-quant-server",
          hostname: "google-vm-raj-quant-server",
          status: "online",
          last_heartbeat: "2026-08-24T10:06:07.000Z",
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
            timestamp: "2026-08-24T10:05:37.000Z",
            tick_rate: 14.5,
            tick_delay_ms: 0.25,
            queue_size: 0,
            queue_wait_ms: 1.5,
            avg_latency_ms: 5.5,
            p95_latency_ms: 7.5,
            p99_latency_ms: 8.5,
            api_success_pct: 100.0,
            signal_fill_rate_pct: 98.0,
            cpu_usage_pct: 11.5,
            memory_mb: 240.0,
            status: "STABLE",
          },
          {
            id: "hlth-2",
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
    expect(
      screen.getByText("Live execution infrastructure and strategy health"),
    ).toBeInTheDocument();

    // 11 Summary Cards
    expect(screen.getByText("CPU Usage")).toBeInTheDocument();
    expect(screen.getByText("Memory")).toBeInTheDocument();
    expect(screen.getByText("Tick Rate")).toBeInTheDocument();
    expect(screen.getByText("Tick Delay")).toBeInTheDocument();
    expect(screen.getByText("Queue Size")).toBeInTheDocument();
    expect(screen.getByText("Queue Wait")).toBeInTheDocument();
    expect(screen.getByText("Avg Latency")).toBeInTheDocument();
    expect(screen.getByText("P95 Latency")).toBeInTheDocument();
    expect(screen.getByText("P99 Latency")).toBeInTheDocument();
    expect(screen.getByText("API Success")).toBeInTheDocument();
    expect(screen.getByText("Signal Fill Rate")).toBeInTheDocument();

    // 5 Chart Panels
    expect(screen.getByText("Tick / Feed Health")).toBeInTheDocument();
    expect(screen.getByText("Execution Latency")).toBeInTheDocument();
    expect(screen.getByText("Queue Health")).toBeInTheDocument();
    expect(screen.getByText("API / Execution Quality")).toBeInTheDocument();
    expect(screen.getByText("Resource Usage")).toBeInTheDocument();

    // 6 Time Range Buttons
    expect(screen.getByText("15 minutes")).toBeInTheDocument();
    expect(screen.getByText("30 minutes")).toBeInTheDocument();
    expect(screen.getByText("1 hour")).toBeInTheDocument();
    expect(screen.getByText("3 hours")).toBeInTheDocument();
    expect(screen.getByText("6 hours")).toBeInTheDocument();
    expect(screen.getByText("24 hours")).toBeInTheDocument();

    // Status Badges
    expect(screen.getByText("STABLE")).toBeInTheDocument();
    expect(screen.getByText("ONLINE")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("renders historical state and offline banner when execution VM is offline", () => {
    hooks.useOpsMachines.mockReturnValue({
      data: [
        {
          id: "mch-agent-google-vm-raj-quant-server",
          name: "google-vm-raj-quant-server",
          hostname: "google-vm-raj-quant-server",
          status: "offline",
          last_heartbeat: "2026-08-24T08:00:00.000Z",
        },
      ],
      isLoading: false,
      isError: false,
    });
    hooks.useOpsSystemHealth.mockReturnValue({
      data: {
        machine_id: "mch-agent-google-vm-raj-quant-server",
        machine_name: "google-vm-raj-quant-server",
        is_live: false,
        current_execution_status: "offline",
        current_health_status: "STABLE",
        last_health_timestamp: "2026-08-24T08:00:00.000Z",
        points: [
          {
            id: "hlth-1",
            machine_id: "mch-agent-google-vm-raj-quant-server",
            timestamp: "2026-08-24T08:00:00.000Z",
            tick_rate: 10.0,
            tick_delay_ms: 0.5,
            queue_size: 0,
            queue_wait_ms: 1.0,
            avg_latency_ms: 5.0,
            p95_latency_ms: 7.0,
            p99_latency_ms: 8.0,
            api_success_pct: 100.0,
            signal_fill_rate_pct: 99.0,
            cpu_usage_pct: 15.0,
            memory_mb: 200.0,
            status: "STABLE",
          },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemHealthPage />);
    expect(screen.getByText("HISTORICAL")).toBeInTheDocument();
    expect(screen.getByText("OFFLINE")).toBeInTheDocument();
    expect(screen.getByText(/Execution VM offline\./)).toBeInTheDocument();
    expect(screen.getByText(/Displaying historical health data through/)).toBeInTheDocument();
  });
});
