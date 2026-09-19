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

const live = vi.hoisted(() => ({
  useMarketPulse: vi.fn(),
  useDevices: vi.fn(),
  usePlatformHealth: vi.fn(),
  useDependencyProbe: vi.fn(),
  useBuildInfo: vi.fn(),
}));
vi.mock("@/lib/markets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/markets")>()),
  useMarketPulse: live.useMarketPulse,
}));
vi.mock("@/lib/devices", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/devices")>()),
  useDevices: live.useDevices,
}));
vi.mock("@/lib/systemHealth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/systemHealth")>()),
  usePlatformHealth: live.usePlatformHealth,
  useDependencyProbe: live.useDependencyProbe,
  useBuildInfo: live.useBuildInfo,
}));

import { WallboardPage } from "@/pages/operations/WallboardPage";
import { useAuth } from "@/stores/auth";

const UPDATED = Date.now();

function ok<T>(data: T, over: Record<string, unknown> = {}) {
  return { data, isLoading: false, isError: false, isSuccess: true, dataUpdatedAt: UPDATED, error: null, ...over };
}
function failed(over: Record<string, unknown> = {}) {
  return { data: undefined, isLoading: false, isError: true, isSuccess: false, dataUpdatedAt: 0, error: new Error("x"), ...over };
}
function idle() {
  return { data: undefined, isLoading: false, isError: false, isSuccess: false, dataUpdatedAt: 0, error: null };
}

const ago = (seconds: number) => new Date(Date.now() - seconds * 1000).toISOString();

function services(overrides: Record<string, number | null> = {}) {
  const ages: Record<string, number | null> = {
    market_data: 1,
    trading_engine: 4,
    scheduler: 40,
    relay: 1,
    email: 1,
    ...overrides,
  };
  const stale: Record<string, number> = { market_data: 30, trading_engine: 30, scheduler: 180, relay: 60, email: 60 };
  return Object.entries(ages).map(([name, age_seconds]) => ({
    name,
    label: name,
    age_seconds,
    stale_after_seconds: stale[name],
  }));
}

function platform(over: Record<string, unknown> = {}) {
  return {
    database: true,
    redis: true,
    outbox_backlog: 0,
    market_data_age_seconds: 1,
    engine_heartbeat_age_seconds: 4,
    active_runs: 2,
    database_latency_ms: 1.84,
    redis_latency_ms: 0.61,
    services: services(),
    checked_at: ago(0),
    ...over,
  };
}

function point(over: Record<string, unknown> = {}) {
  return {
    machine_id: "m1",
    timestamp: ago(5),
    tick_rate: 40,
    tick_delay_ms: 1.2,
    queue_size: 0,
    queue_wait_ms: 1.1,
    avg_latency_ms: 3.2,
    p95_latency_ms: 7.5,
    p99_latency_ms: 11.4,
    api_success_pct: 99.7,
    api_success_rate: 99.7,
    signal_fill_rate_pct: 97.2,
    signal_fill_rate: 97.2,
    cpu_usage_pct: 31,
    cpu_usage: 31,
    memory_mb: 1880,
    status: "STABLE",
    ...over,
  };
}

function telemetry(over: Record<string, unknown> = {}, latest = point()) {
  return {
    machine_id: "m1",
    machine_name: "trading-01",
    is_live: true,
    current_execution_status: "online",
    current_health_status: "STABLE",
    last_health_timestamp: latest.timestamp,
    latest,
    points: [point({ timestamp: ago(20), cpu_usage: 28 }), latest],
    ...over,
  };
}

const machine = (over: Record<string, unknown> = {}) => ({
  id: "m1",
  name: "trading-01",
  hostname: "trading-01",
  agent_id: "a1",
  status: "online",
  cpu: 22,
  ram: 41,
  disk: 55,
  last_heartbeat: ago(8),
  last_successful_upload: ago(8),
  queue_depth: 0,
  oldest_pending_age_sec: 0,
  transport_state: "connected",
  internet_ms: 18,
  broker_ping_ms: 31,
  ...over,
});

/** A board where every component is reporting well. */
function healthy() {
  hooks.useOpsOverview.mockReturnValue(
    ok({ machine_count: 1, online_machines: 1, closed_trade_count: 4, total_pnl: 0, awaiting_telemetry: false, telemetry_configured: true }),
  );
  hooks.useOpsMachines.mockReturnValue(ok([machine()]));
  hooks.useOpsAlerts.mockReturnValue(ok([]));
  hooks.useOpsSystemHealth.mockReturnValue(ok(telemetry()));
  hooks.useMonitoringState.mockReturnValue(
    ok({
      receiver_deployment_environment: "staging",
      configured: true,
      count: 3,
      items: [{ freshness: { status: "FRESH" } }, { freshness: { status: "STALE" } }, { freshness: { status: "UNKNOWN" } }],
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
        first_seen_at: ago(3600),
        last_seen_at: ago(60),
      },
    ]),
  );
  hooks.useMarketQuotes.mockReturnValue(
    ok([{ symbol: "RELIANCE", name: "Reliance", yahoo_symbol: "RELIANCE.NS", price: "1", previous_close: "1", change: "0", change_pct: "0.1", currency: "INR", as_of: ago(90) }]),
  );
  live.useMarketPulse.mockReturnValue({
    isSuccess: true,
    isError: false,
    data: {
      session: { state: "closed", as_of: ago(0), note: "" },
      universe: { source: "nse", trade_date: new Date().toISOString().slice(0, 10) },
      indices: [{ symbol: "^NSEI", name: "NIFTY 50", price: 23346.4, change_pct: 0.55 }],
      vix: { symbol: "^INDIAVIX", name: "INDIA VIX", price: 11.39, change_pct: -13.6 },
      breadth: { advances: 145, declines: 60, unchanged: 5, pct_advancing: 69 },
      regime: { volatility: { label: "Calm" } },
      institutional_flows: [{ trade_date: "2026-09-18", fii_net: 599.54 }],
    },
  });
  live.useDevices.mockReturnValue({ data: [], isSuccess: true, isError: false });
  live.usePlatformHealth.mockReturnValue(ok(platform()));
  live.useDependencyProbe.mockReturnValue(
    ok({
      status: "ok",
      round_trip_ms: 42,
      dependencies: [
        { name: "postgres", healthy: true, detail: null },
        { name: "redis", healthy: true, detail: null },
      ],
    }),
  );
  live.useBuildInfo.mockReturnValue(ok({ service: "algo-platform", version: "0.9.0", build_sha: "191fd50e4c", environment: "production" }));
}

const view = () =>
  render(
    <MemoryRouter>
      <WallboardPage />
    </MemoryRouter>,
  );

const tile = (title: string) => screen.getByRole("article", { name: title });
const panel = (title: string) => screen.getByRole("region", { name: title });
const kpi = (title: string) => screen.getByRole("group", { name: title });
const overall = () => screen.getByRole("status", { name: "Overall status" });

function setAdmin(isAdmin: boolean) {
  useAuth.setState({ user: { is_platform_admin: isAdmin } as never });
}

describe("operations wallboard", () => {
  beforeEach(() => {
    Object.values(hooks).forEach((fn) => fn.mockReset());
    Object.values(live).forEach((fn) => fn.mockReset());
    setAdmin(true);
    healthy();
  });
  afterEach(() => {
    vi.useRealTimers();
    useAuth.setState({ user: null });
  });

  /* ------------------------------ platform ------------------------------ */

  it("shows every platform service with a real signal behind it", () => {
    view();
    expect(within(tile("API")).getByText("42 ms")).toBeInTheDocument();
    expect(within(tile("Database")).getByText("1.8 ms")).toBeInTheDocument();
    expect(within(tile("Redis cache")).getByText("0.6 ms")).toBeInTheDocument();
    for (const name of ["Market data feed", "Trading engine", "Scheduler", "Outbox relay", "E-mail worker"]) {
      expect(within(tile(name)).getByText("Running")).toBeInTheDocument();
      expect(within(tile(name)).getByText("HEALTHY")).toBeInTheDocument();
    }
    expect(within(tile("Outbox relay")).getByText(/backlog 0/)).toBeInTheDocument();
    expect(within(tile("Trading engine")).getByText(/2 active runs/)).toBeInTheDocument();
  });

  it("says all systems operational when every required check is healthy", () => {
    view();
    // No devices are registered, which is not a fault and does not block the verdict.
    expect(within(overall()).getByText("HEALTHY")).toBeInTheDocument();
    expect(within(overall()).getByText(/All systems operational/)).toBeInTheDocument();
  });

  it("calls a process with no heartbeat CRITICAL and a late one STALE", () => {
    live.usePlatformHealth.mockReturnValue(ok(platform({ services: services({ scheduler: 400, email: null }) })));
    view();
    expect(within(tile("Scheduler")).getByText("Overdue")).toBeInTheDocument();
    expect(within(tile("Scheduler")).getByText("STALE")).toBeInTheDocument();
    expect(within(tile("E-mail worker")).getByText("No heartbeat")).toBeInTheDocument();
    expect(within(tile("E-mail worker")).getByText("CRITICAL")).toBeInTheDocument();
    expect(within(overall()).getByText("CRITICAL")).toBeInTheDocument();
  });

  it("shows the database down when the API server's probe fails", () => {
    live.usePlatformHealth.mockReturnValue(ok(platform({ database: false, database_latency_ms: null })));
    view();
    expect(within(tile("Database")).getByText("Unreachable")).toBeInTheDocument();
    expect(within(tile("Database")).getByText("CRITICAL")).toBeInTheDocument();
  });

  it("never calls the database healthy without a probe answering", () => {
    live.usePlatformHealth.mockReturnValue(failed());
    live.useDependencyProbe.mockReturnValue(failed());
    view();
    const database = tile("Database");
    expect(within(database).getByText("UNKNOWN", { selector: "p" })).toBeInTheDocument();
    expect(within(database).queryByText("HEALTHY")).not.toBeInTheDocument();
    expect(within(overall()).queryByText("HEALTHY")).not.toBeInTheDocument();
  });

  it("keeps the last known value but labels it STALE when a check starts failing", () => {
    live.usePlatformHealth.mockReturnValue({ ...ok(platform()), isError: true });
    view();
    expect(within(tile("Database")).getByText("1.8 ms")).toBeInTheDocument();
    expect(within(tile("Database")).getByText("STALE")).toBeInTheDocument();
  });

  it("uses the public probe for non-admins and keeps process detail for admins", () => {
    setAdmin(false);
    live.usePlatformHealth.mockReturnValue(idle());
    view();
    expect(within(tile("Database")).getByText("Reachable")).toBeInTheDocument();
    expect(within(tile("Database")).getByText("HEALTHY")).toBeInTheDocument();
    expect(within(tile("Scheduler")).getByText(/visible to platform admins/)).toBeInTheDocument();
    // Five processes unseen: the board cannot claim the whole system is healthy.
    expect(within(overall()).queryByText("HEALTHY")).not.toBeInTheDocument();
    expect(live.usePlatformHealth).toHaveBeenCalledWith(false);
  });

  it("tells an admin without 2FA why process health is hidden", async () => {
    const { ApiError } = await import("@/lib/api");
    live.usePlatformHealth.mockReturnValue(failed({ error: new ApiError(403, "mfa_required", "2FA required") }));
    view();
    expect(within(tile("Scheduler")).getByText(/turn on 2FA/)).toBeInTheDocument();
  });

  /* ----------------------------- data sources ---------------------------- */

  it("marks a partially-online agent fleet DEGRADED and a silent one CRITICAL", () => {
    hooks.useOpsOverview.mockReturnValue(
      ok({ machine_count: 3, online_machines: 1, closed_trade_count: 0, total_pnl: 0, awaiting_telemetry: false, telemetry_configured: true }),
    );
    const first = view();
    expect(within(tile("Execution agents")).getByText("1/3 online")).toBeInTheDocument();
    expect(within(tile("Execution agents")).getByText("DEGRADED")).toBeInTheDocument();
    first.unmount();

    hooks.useOpsOverview.mockReturnValue(
      ok({ machine_count: 3, online_machines: 0, closed_trade_count: 0, total_pnl: 0, awaiting_telemetry: false, telemetry_configured: true }),
    );
    view();
    expect(within(tile("Execution agents")).getByText("0/3 online")).toBeInTheDocument();
    expect(within(tile("Execution agents")).getByText("CRITICAL")).toBeInTheDocument();
  });

  it("does not call a receiver healthy just because its store is reachable", () => {
    hooks.useMonitoringState.mockReturnValue(ok({ receiver_deployment_environment: "staging", configured: true, count: 0, items: [] }));
    view();
    expect(within(tile("LLS receiver")).getByText(/no messages received/i)).toBeInTheDocument();
    expect(within(tile("LLS receiver")).queryByText("HEALTHY")).not.toBeInTheDocument();
  });

  it("distinguishes an unconfigured receiver from an empty one", () => {
    hooks.useMonitoringState.mockReturnValue(ok({ receiver_deployment_environment: "UNKNOWN", configured: false, count: 0, items: [] }));
    view();
    expect(within(tile("LLS receiver")).getByText(/not configured/i)).toBeInTheDocument();
  });

  it("flags the built-in F&O list when NSE has not been captured", () => {
    live.useMarketPulse.mockReturnValue({
      isSuccess: true,
      isError: false,
      data: { ...healthyPulse(), universe: { source: "built_in", trade_date: null } },
    });
    view();
    expect(within(tile("NSE snapshots")).getByText("Built-in list")).toBeInTheDocument();
    expect(within(tile("NSE snapshots")).getByText("DEGRADED")).toBeInTheDocument();
  });

  /* ------------------------------ telemetry ------------------------------ */

  it("brings the System Health metrics onto the board", () => {
    view();
    const board = panel("Execution telemetry");
    expect(within(board).getByText("trading-01")).toBeInTheDocument();
    expect(within(board).getByText("LIVE")).toBeInTheDocument();
    expect(within(kpi("CPU")).getByText("31.0")).toBeInTheDocument();
    expect(within(kpi("P99 latency")).getByText("11.40")).toBeInTheDocument();
    expect(within(kpi("Memory")).getByText("1,880")).toBeInTheDocument();
    expect(within(board).getByText("Execution latency (ms)")).toBeInTheDocument();
  });

  it("prints API success as the percentage the agent reported", () => {
    view();
    // 99.7 is already a percentage; it must not be multiplied into 9970%.
    expect(within(kpi("API success")).getByText("99.7")).toBeInTheDocument();
    expect(within(kpi("API success")).getByText("HEALTHY")).toBeInTheDocument();
  });

  it("ignores api_success_pct=100 when the agent reported no success rate", () => {
    const latest = point({ api_success_pct: 100, api_success_rate: null });
    hooks.useOpsSystemHealth.mockReturnValue(ok(telemetry({}, latest)));
    view();
    expect(within(kpi("API success")).getByText("UNKNOWN")).toBeInTheDocument();
    expect(within(kpi("API success")).queryByText(/100/)).not.toBeInTheDocument();
  });

  it("labels an agent's last figures STALE when it is no longer reporting", () => {
    const latest = point({ timestamp: ago(3 * 3600) });
    hooks.useOpsSystemHealth.mockReturnValue(ok(telemetry({ is_live: false }, latest)));
    view();
    const board = panel("Execution telemetry");
    expect(within(board).getByText("HISTORICAL")).toBeInTheDocument();
    expect(within(board).getByText(/not reporting right now/)).toBeInTheDocument();
    expect(within(kpi("CPU")).getByText("STALE")).toBeInTheDocument();
    expect(within(kpi("CPU")).getByText("31.0")).toBeInTheDocument();
  });

  it("says so plainly when the agent has never reported", () => {
    hooks.useOpsSystemHealth.mockReturnValue(ok({ ...telemetry(), latest: null, points: [], last_health_timestamp: null, is_live: false }));
    view();
    expect(screen.getByText("NO EXECUTION TELEMETRY YET")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "CPU" })).not.toBeInTheDocument();
  });

  it("lets the viewer switch between execution machines", async () => {
    hooks.useOpsMachines.mockReturnValue(ok([machine(), machine({ id: "m2", name: "trading-02", hostname: "trading-02" })]));
    view();
    await userEvent.click(screen.getByRole("button", { name: "trading-02" }));
    expect(hooks.useOpsSystemHealth).toHaveBeenLastCalledWith(
      expect.objectContaining({ machine_id: "m2" }),
      expect.anything(),
    );
    expect(screen.getByRole("button", { name: "trading-02" })).toHaveAttribute("aria-pressed", "true");
  });

  /* ------------------------------- incidents ------------------------------ */

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
    view();
    expect(screen.getByText("INCIDENT STATE UNKNOWN")).toBeInTheDocument();
    expect(screen.queryByText("NO ACTIVE INCIDENTS")).not.toBeInTheDocument();
  });

  it("lists incidents worst-first with severity as text", () => {
    hooks.useOpsAlerts.mockReturnValue(
      ok([
        { id: "e1", time: ago(600), received_at: null, category: null, severity: "warning", source: "engine", message: "queue rising", machine_id: null, event_type: "alert", strategy: null, symbol: null, payload_summary: null },
        { id: "e2", time: ago(60), received_at: null, category: null, severity: "critical", source: "broker", message: "session lost", machine_id: null, event_type: "alert", strategy: null, symbol: null, payload_summary: null },
      ]),
    );
    view();
    const items = within(panel("Incidents")).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("CRITICAL");
    expect(items[0]).toHaveTextContent("session lost");
    expect(items[1]).toHaveTextContent("WARNING");
  });

  /* ------------------------------ connection ------------------------------ */

  it("shows CONNECTION DEGRADED without blanking the board", () => {
    hooks.useOpsMachines.mockReturnValue(failed());
    view();
    expect(screen.getByText("CONNECTION DEGRADED")).toBeInTheDocument();
    expect(within(tile("Execution agents")).getByText("1/1 online")).toBeInTheDocument();
    expect(within(tile("API")).getByText("DEGRADED")).toBeInTheDocument();
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
    expect(screen.getByText("CONNECTED")).toBeInTheDocument();
  });

  it("always shows the overall status and last update, even with nothing answering", () => {
    for (const fn of Object.values(hooks)) fn.mockReturnValue(failed());
    live.usePlatformHealth.mockReturnValue(failed());
    live.useDependencyProbe.mockReturnValue(failed());
    view();
    expect(overall()).toBeInTheDocument();
    expect(screen.getByText("No update yet", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("LAST SUCCESSFUL UPDATE", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("INCIDENT STATE UNKNOWN")).toBeInTheDocument();
    expect(within(overall()).queryByText("HEALTHY")).not.toBeInTheDocument();
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

  /* ------------------------------ display mode ----------------------------- */

  it("offers display mode and fullscreen with an obvious way out", async () => {
    view();
    expect(screen.getByTestId("wallboard").className).not.toContain("fixed");

    await userEvent.click(screen.getByRole("button", { name: "Display mode" }));
    expect(screen.getByTestId("wallboard").className).toContain("fixed");
    // Never trapped: the way out is on screen the whole time.
    expect(screen.getByRole("button", { name: "Exit display mode" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Exit" })).toHaveAttribute("href", "/app/dashboard");

    await userEvent.click(screen.getByRole("button", { name: "Exit display mode" }));
    expect(screen.getByTestId("wallboard").className).not.toContain("fixed");
    expect(screen.getByRole("button", { name: "Fullscreen" })).toBeInTheDocument();
  });

  it("toggles display mode from the keyboard and leaves it on Escape", async () => {
    view();
    await userEvent.keyboard("d");
    expect(screen.getByTestId("wallboard").className).toContain("fixed");
    await userEvent.keyboard("{Escape}");
    expect(screen.getByTestId("wallboard").className).not.toContain("fixed");
  });

  it("locks to one screen on wall-sized displays and scrolls on smaller ones", () => {
    view();
    const board = screen.getByTestId("wallboard");
    expect(board.className).toContain("wall:h-[100dvh]");
    expect(board.className).toContain("wall:overflow-hidden");
    expect(board.className).toContain("min-h-[100dvh]");
  });

  /* ------------------------------ market strip ----------------------------- */

  it("shows the live market strip, and UNKNOWN when it has no data", () => {
    view();
    const strip = screen.getByTestId("market-strip");
    expect(within(strip).getByText("23,346.4")).toBeInTheDocument();
    expect(within(strip).getByText("145 / 60")).toBeInTheDocument();
    expect(within(strip).getByText("600")).toBeInTheDocument();
  });

  it("prints UNKNOWN in the market strip rather than a made-up number", () => {
    live.useMarketPulse.mockReturnValue({ data: undefined, isSuccess: false, isError: true });
    view();
    const strip = screen.getByTestId("market-strip");
    expect(within(strip).getAllByText("UNKNOWN").length).toBeGreaterThan(0);
    expect(within(strip).queryByText("0")).not.toBeInTheDocument();
  });

  /* --------------------------------- fleet -------------------------------- */

  it("marks the device fleet DEGRADED when a device goes silent", () => {
    live.useDevices.mockReturnValue({
      isSuccess: true,
      data: [
        { id: "d1", name: "VPS Mumbai 1", kind: "vps", status: "online", last_seen_at: ago(20), health: { cpu: 38, ram: 71, disk: 54 } },
        { id: "d2", name: "MT5 Desk", kind: "mt5", status: "offline", last_seen_at: ago(3 * 3600), health: null },
      ],
    });
    view();
    expect(within(tile("Trading devices")).getByText("DEGRADED")).toBeInTheDocument();
    const fleet = panel("Fleet");
    expect(within(fleet).getByText("OFFLINE")).toBeInTheDocument();
    expect(within(fleet).getByText("38%")).toBeInTheDocument();
    // A device that sent no health shows a dash, never 0%.
    expect(within(fleet).queryByText("0%")).not.toBeInTheDocument();
  });

  it("does not call an empty fleet healthy", () => {
    view();
    expect(within(panel("Fleet")).getByText("NO DEVICES REGISTERED")).toBeInTheDocument();
    expect(within(tile("Trading devices")).queryByText("HEALTHY")).not.toBeInTheDocument();
  });

  /* ------------------------------ read-only ------------------------------ */

  it("names what the platform does not measure instead of showing a zero", () => {
    view();
    expect(screen.getByText(/NOT MEASURED:/)).toHaveTextContent(/ingestion rate/);
  });

  it("offers no trading control of any kind", () => {
    const { container } = view();
    for (const word of [/\bbuy\b/i, /\bsell\b/i, /\border\b/i, /square off/i, /\bplace\b/i]) {
      expect(container.textContent).not.toMatch(word);
    }
    expect(container.querySelector("form")).toBeNull();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Display mode", "Fullscreen"]);
  });
});

function healthyPulse() {
  return {
    session: { state: "closed", as_of: ago(0), note: "" },
    universe: { source: "nse", trade_date: new Date().toISOString().slice(0, 10) },
    indices: [],
    vix: { symbol: "^INDIAVIX", name: "INDIA VIX", price: 11.39, change_pct: -13.6 },
    breadth: { advances: 145, declines: 60, unchanged: 5, pct_advancing: 69 },
    regime: { volatility: { label: "Calm" } },
    institutional_flows: [],
  };
}
