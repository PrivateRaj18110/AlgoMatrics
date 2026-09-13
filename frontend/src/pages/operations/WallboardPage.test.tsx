import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => ({
  useMarketQuotes: vi.fn(),
  useMonitoringSources: vi.fn(),
  useMonitoringState: vi.fn(),
  useOpsAlerts: vi.fn(),
  useOpsMachines: vi.fn(),
  useOpsOverview: vi.fn(),
  useOpsSystemHealth: vi.fn(),
}));
vi.mock("@/lib/hooks", () => hooks);

import { WallboardPage } from "@/pages/operations/WallboardPage";

const UPDATED = 1_757_760_000_000;

function ok<T>(data: T, over: Record<string, unknown> = {}) {
  return { data, isLoading: false, isError: false, isSuccess: true, dataUpdatedAt: UPDATED, ...over };
}
function failed(over: Record<string, unknown> = {}) {
  return { data: undefined, isLoading: false, isError: true, isSuccess: false, dataUpdatedAt: 0, ...over };
}

/** A wallboard where every component is reporting well. */
function healthy() {
  hooks.useOpsOverview.mockReturnValue(
    ok({
      machine_count: 2,
      online_machines: 2,
      closed_trade_count: 4,
      total_pnl: 0,
      awaiting_telemetry: false,
      telemetry_configured: true,
    }),
  );
  hooks.useOpsMachines.mockReturnValue(
    ok([
      {
        id: "m1",
        name: "trading-01",
        hostname: "trading-01",
        agent_id: "a1",
        status: "online",
        cpu: 22,
        ram: 41,
        disk: 55,
        last_heartbeat: "2026-09-13T09:59:00Z",
        last_successful_upload: "2026-09-13T09:59:00Z",
        queue_depth: 0,
        oldest_pending_age_sec: 0,
        transport_state: "connected",
        internet_ms: 18,
        broker_ping_ms: 31,
      },
    ]),
  );
  hooks.useOpsAlerts.mockReturnValue(ok([]));
  hooks.useOpsSystemHealth.mockReturnValue(
    ok({
      machine_id: "m1",
      machine_name: "trading-01",
      is_live: true,
      current_execution_status: "running",
      current_health_status: "STABLE",
      last_health_timestamp: "2026-09-13T09:59:00Z",
      latest: { machine_id: "m1", timestamp: "2026-09-13T09:59:00Z", api_success_rate: 0.997 },
      points: [],
    }),
  );
  hooks.useMonitoringState.mockReturnValue(
    ok({
      receiver_deployment_environment: "staging",
      configured: true,
      count: 3,
      items: [
        { freshness: { status: "FRESH" } },
        { freshness: { status: "STALE" } },
        { freshness: { status: "UNKNOWN" } },
      ],
    }),
  );
  hooks.useMonitoringSources.mockReturnValue(
    ok([
      {
        source_id: "lls-1",
        source_instance: "i-1",
        last_accepted_sequence: "9",
        last_accepted_message_id: "mon1/abc",
        accepted_count: 9,
        duplicate_count: 1,
        refused_gap_count: 0,
        refused_old_count: 0,
        observed_refusals: [],
        first_seen_at: "2026-09-13T08:00:00Z",
        last_seen_at: "2026-09-13T09:58:00Z",
      },
    ]),
  );
  hooks.useMarketQuotes.mockReturnValue(
    ok([{ symbol: "RELIANCE", name: "Reliance", yahoo_symbol: "RELIANCE.NS", price: "1", previous_close: "1", change: "0", change_pct: "0.1", currency: "INR", as_of: "2026-09-13T09:45:00Z" }]),
  );
}

const view = () =>
  render(
    <MemoryRouter>
      <WallboardPage />
    </MemoryRouter>,
  );

/** The status card whose label matches, as a container for its own assertions.
 *  Matched on the heading element: short labels like "API" also appear in the
 *  footer, and a bare text query would be ambiguous. */
function card(label: string) {
  const heading = screen.getAllByText(label).find((node) => node.tagName === "H2");
  return heading!.closest("section")!;
}

/** The top bar, for assertions about overall status that also appear below. */
function header() {
  return screen.getByText("ALGOMATRIC SYSTEM HEALTH").closest("header")!;
}

describe("operations wallboard", () => {
  beforeEach(() => {
    Object.values(hooks).forEach((fn) => fn.mockReset());
    healthy();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("reports HEALTHY components but never claims the database is healthy", () => {
    view();

    expect(within(card("SYSTEM")).getByText("2/2 ONLINE")).toBeInTheDocument();
    expect(within(card("API")).getByText("REACHABLE")).toBeInTheDocument();

    // The canonical false-health case: a 200 from the API says nothing about
    // Postgres, so this card must stay UNKNOWN even when everything else is up.
    const database = card("DATABASE");
    // Both the headline value and the state chip read UNKNOWN.
    expect(within(database).getAllByText("UNKNOWN")).toHaveLength(2);
    expect(within(database).getByText(/no database health signal/i)).toBeInTheDocument();
  });

  it("never shows an overall HEALTHY while any component is UNKNOWN", () => {
    view();
    const bar = header();
    // DATABASE is structurally UNKNOWN, so the board as a whole cannot be HEALTHY.
    expect(within(bar).queryByText("HEALTHY")).not.toBeInTheDocument();
    expect(within(bar).getAllByText("UNKNOWN").length).toBeGreaterThan(0);
  });

  it("marks a partially-online fleet DEGRADED", () => {
    hooks.useOpsOverview.mockReturnValue(
      ok({ machine_count: 3, online_machines: 1, closed_trade_count: 0, total_pnl: 0, awaiting_telemetry: false, telemetry_configured: true }),
    );
    view();

    const system = card("SYSTEM");
    expect(within(system).getByText("1/3 ONLINE")).toBeInTheDocument();
    expect(within(system).getByText("DEGRADED")).toBeInTheDocument();
  });

  it("marks a fully-offline fleet CRITICAL", () => {
    hooks.useOpsOverview.mockReturnValue(
      ok({ machine_count: 3, online_machines: 0, closed_trade_count: 0, total_pnl: 0, awaiting_telemetry: false, telemetry_configured: true }),
    );
    view();

    const system = card("SYSTEM");
    expect(within(system).getByText("0/3 ONLINE")).toBeInTheDocument();
    expect(within(system).getByText("CRITICAL")).toBeInTheDocument();
  });

  it("keeps the last known value but labels it STALE when a query is failing", () => {
    hooks.useOpsMachines.mockReturnValue({
      ...ok([{ id: "m1", name: "t", hostname: null, agent_id: null, status: "online", cpu: 71, ram: 40, disk: 50, last_heartbeat: null, last_successful_upload: null, queue_depth: 0, oldest_pending_age_sec: 0 }]),
      isError: true,
    });
    view();

    const cpu = screen.getByText("CPU — PEAK ACROSS MACHINES").nextElementSibling!;
    expect(cpu).toHaveTextContent("71%");
    expect(cpu).toHaveAttribute("title", expect.stringMatching(/last known/i));
  });

  it("shows UNKNOWN, not zero, for metrics the platform does not collect", () => {
    view();

    for (const label of ["FEEDS CONNECTED", "FEED ERRORS", "INGESTION RATE", "QUARANTINED", "INGESTION LATENCY", "POSTGRESQL", "DATABASE CONNECTIONS", "WORKER STATUS", "PROCESS MEMORY"]) {
      const value = screen.getByText(label).nextElementSibling!;
      expect(value, `${label} must be UNKNOWN`).toHaveTextContent("UNKNOWN");
      expect(value).not.toHaveTextContent(/^0$/);
    }
  });

  it("ignores api_success_pct=100 when the agent reported no success rate", () => {
    hooks.useOpsSystemHealth.mockReturnValue(
      ok({
        machine_id: "m1",
        machine_name: "t",
        is_live: false,
        current_execution_status: "offline",
        current_health_status: null,
        last_health_timestamp: null,
        // Exactly what the ops API returns for an agent that reported nothing.
        latest: { machine_id: "m1", timestamp: "2026-09-13T09:00:00Z", api_success_pct: 100, api_success_rate: null },
        points: [],
      }),
    );
    view();

    const value = screen.getByText("API SUCCESS RATE").nextElementSibling!;
    expect(value).toHaveTextContent("UNKNOWN");
    expect(value).not.toHaveTextContent("100");
  });

  it("does not call a receiver healthy just because its store is reachable", () => {
    hooks.useMonitoringState.mockReturnValue(
      ok({ receiver_deployment_environment: "staging", configured: true, count: 0, items: [] }),
    );
    view();

    const receiver = card("MONITORING RECEIVER");
    expect(within(receiver).getAllByText("UNKNOWN")).toHaveLength(2);
    expect(within(receiver).getByText(/no messages received/i)).toBeInTheDocument();
  });

  it("distinguishes an unconfigured receiver from an empty one", () => {
    hooks.useMonitoringState.mockReturnValue(
      ok({ receiver_deployment_environment: "UNKNOWN", configured: false, count: 0, items: [] }),
    );
    view();
    expect(within(card("MONITORING RECEIVER")).getByText(/not configured/i)).toBeInTheDocument();
  });

  it("says NO ACTIVE INCIDENTS only when the store actually answered", () => {
    view();
    expect(screen.getByText("NO ACTIVE INCIDENTS")).toBeInTheDocument();
  });

  it("says INCIDENT STATE UNKNOWN when the incident store failed", () => {
    hooks.useOpsAlerts.mockReturnValue(failed());
    view();

    expect(screen.getByText("INCIDENT STATE UNKNOWN")).toBeInTheDocument();
    expect(screen.queryByText("NO ACTIVE INCIDENTS")).not.toBeInTheDocument();
  });

  it("says INCIDENT STATE UNKNOWN when telemetry is unconfigured and the empty list means nothing", () => {
    hooks.useOpsOverview.mockReturnValue(
      ok({ machine_count: null, online_machines: null, closed_trade_count: null, total_pnl: null, awaiting_telemetry: true, telemetry_configured: false }),
    );
    hooks.useOpsAlerts.mockReturnValue(ok([]));
    view();

    expect(screen.getByText("INCIDENT STATE UNKNOWN")).toBeInTheDocument();
    expect(screen.queryByText("NO ACTIVE INCIDENTS")).not.toBeInTheDocument();
  });

  it("lists multiple incidents worst-first with severity as text", () => {
    hooks.useOpsAlerts.mockReturnValue(
      ok([
        { id: "e1", time: "2026-09-13T09:10:00Z", received_at: null, category: null, severity: "warning", source: "engine", message: "queue rising", machine_id: null, event_type: "alert", strategy: null, symbol: null, payload_summary: null },
        { id: "e2", time: "2026-09-13T09:20:00Z", received_at: null, category: null, severity: "critical", source: "broker", message: "session lost", machine_id: null, event_type: "alert", strategy: null, symbol: null, payload_summary: null },
      ]),
    );
    view();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("CRITICAL");
    expect(items[0]).toHaveTextContent("session lost");
    expect(items[1]).toHaveTextContent("WARNING");
  });

  it("shows CONNECTION DEGRADED without blanking the board", () => {
    hooks.useOpsMachines.mockReturnValue(failed());
    view();

    expect(screen.getByText("CONNECTION DEGRADED")).toBeInTheDocument();
    // Panels that still have data keep rendering it.
    expect(within(card("SYSTEM")).getByText("2/2 ONLINE")).toBeInTheDocument();
    expect(screen.getByText("ALGOMATRIC SYSTEM HEALTH")).toBeInTheDocument();
  });

  it("recovers automatically when the API comes back", () => {
    hooks.useOpsMachines.mockReturnValue(failed());
    const rendered = view();
    expect(screen.getByText("CONNECTION DEGRADED")).toBeInTheDocument();

    healthy();
    rendered.rerender(
      <MemoryRouter>
        <WallboardPage />
      </MemoryRouter>,
    );
    expect(screen.queryByText("CONNECTION DEGRADED")).not.toBeInTheDocument();
    expect(within(header()).getByText("CONNECTED")).toBeInTheDocument();
  });

  it("leaves no timers behind across repeated mount and unmount", () => {
    vi.useFakeTimers();
    const before = vi.getTimerCount();

    for (let round = 0; round < 3; round += 1) {
      const rendered = view();
      vi.advanceTimersByTime(5_000);
      rendered.unmount();
    }

    expect(vi.getTimerCount()).toBe(before);
  });

  it("offers display mode and fullscreen with an obvious way out", async () => {
    view();

    const board = screen.getByTestId("wallboard");
    expect(board.className).not.toContain("fixed");

    await userEvent.click(screen.getByRole("button", { name: "DISPLAY MODE" }));
    expect(screen.getByTestId("wallboard").className).toContain("fixed");
    // Never trapped: the exit control is present the whole time.
    expect(screen.getByRole("button", { name: "EXIT DISPLAY MODE" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "EXIT" })).toHaveAttribute("href", "/app/dashboard");

    await userEvent.click(screen.getByRole("button", { name: "EXIT DISPLAY MODE" }));
    expect(screen.getByTestId("wallboard").className).not.toContain("fixed");
    expect(screen.getByRole("button", { name: "FULLSCREEN" })).toBeInTheDocument();
  });

  it("fills the viewport height and never scrolls", () => {
    view();
    const board = screen.getByTestId("wallboard");
    expect(board.className).toContain("h-[100dvh]");
    expect(board.className).toContain("overflow-hidden");
  });

  it("always shows overall status, last update and freshness regardless of data", () => {
    hooks.useOpsOverview.mockReturnValue(failed());
    hooks.useMonitoringState.mockReturnValue(failed());
    hooks.useMonitoringSources.mockReturnValue(failed());
    hooks.useMarketQuotes.mockReturnValue(failed());
    hooks.useOpsMachines.mockReturnValue(failed());
    hooks.useOpsAlerts.mockReturnValue(failed());
    hooks.useOpsSystemHealth.mockReturnValue(failed());
    view();

    expect(screen.getByText("ALGOMATRIC SYSTEM HEALTH")).toBeInTheDocument();
    expect(screen.getByText("LAST UPDATE")).toBeInTheDocument();
    expect(screen.getByText("LAST SUCCESSFUL UPDATE")).toBeInTheDocument();
    expect(screen.getByText("INCIDENT STATE UNKNOWN")).toBeInTheDocument();
    // Nothing has ever succeeded, so there is no last update to claim.
    expect(screen.getByText("LAST UPDATE").nextElementSibling).toHaveTextContent("UNKNOWN");
  });

  it("offers no trading control of any kind", () => {
    const { container } = view();

    for (const word of [/\bbuy\b/i, /\bsell\b/i, /\border\b/i, /square off/i, /\bplace\b/i]) {
      expect(container.textContent).not.toMatch(word);
    }
    expect(container.querySelector("form")).toBeNull();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "DISPLAY MODE",
      "FULLSCREEN",
    ]);
  });
});
