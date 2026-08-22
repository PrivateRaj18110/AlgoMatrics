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
}));

vi.mock("@/lib/hooks", () => hooks);

import {
  ClosedTradesPage,
  EngineStrategiesPage,
  EventsPage,
  MachinesPage,
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
});
