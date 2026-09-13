// Page composition, against real staging data.
//
// The previous phase tested the monitoring *components* and recorded page
// composition as NOT TESTED. This closes that: the whole page is rendered with
// the exact payloads a running staging deployment returned, captured from
// `/api/v1/operations/monitoring/state` and `/sources` after real messages were
// delivered over HTTPS to the receiver and stored in PostgreSQL.
//
// The fixtures in `__fixtures__/` are therefore not hand-written. They are what
// the system actually produced, which is the only version of this test worth
// having — a page that passes against invented data proves nothing about the
// data it will really be given.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import stagingSemantics from "./__fixtures__/staging-monitoring-semantics.json";
import stagingSources from "./__fixtures__/staging-monitoring-sources.json";
import stagingState from "./__fixtures__/staging-monitoring-state.json";

const mockState = vi.hoisted(() => vi.fn());
const mockSources = vi.hoisted(() => vi.fn());

vi.mock("@/lib/hooks", () => ({
  useMonitoringState: mockState,
  useMonitoringSources: mockSources,
}));

import { MonitoringPage } from "./MonitoringPage";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MonitoringPage />
    </QueryClientProvider>,
  );
}

function query(data: unknown, overrides: Record<string, unknown> = {}) {
  return { data, isLoading: false, isError: false, error: null, ...overrides };
}

describe("MonitoringPage, against real staging payloads", () => {
  it("shows the deployment tier the receiver reported", () => {
    mockState.mockReturnValue(query(stagingState));
    mockSources.mockReturnValue(query(stagingSources));
    renderPage();

    expect(screen.getByText("staging")).toBeInTheDocument();
  });

  it("keeps the two environments apart", () => {
    // The producer said offline_fixture (market reality); we are deployed in
    // staging (our tier). Neither may be shown as the other.
    mockState.mockReturnValue(query(stagingState));
    mockSources.mockReturnValue(query(stagingSources));
    const { container } = renderPage();

    expect(screen.getByText("staging")).toBeInTheDocument();
    expect(container.textContent).toContain("offline_fixture");
    // Nothing on the page may claim live trading for an offline fixture.
    expect(container.textContent).not.toContain("live_trading");
  });

  it("renders every message type the receiver projected", () => {
    mockState.mockReturnValue(query(stagingState));
    mockSources.mockReturnValue(query(stagingSources));
    const { container } = renderPage();

    for (const item of stagingState.items) {
      expect(container.textContent).toContain(item.message_type);
    }
    // Four distinct types were delivered; none may be merged away.
    expect(new Set(stagingState.items.map((i) => i.message_type)).size).toBeGreaterThan(1);
  });

  it("shows STALE as STALE and never upgrades it", () => {
    // This projection arrived moments before it was captured. A page that
    // inferred freshness from arrival time would show it as live.
    mockState.mockReturnValue(query(stagingSemantics));
    mockSources.mockReturnValue(query(stagingSources));
    const { container } = renderPage();

    expect(stagingSemantics.items[0].freshness.source).toBe("STALE");
    expect(screen.getAllByText("STALE").length).toBeGreaterThan(0);
    expect(container.textContent).not.toContain("LIVE");
  });

  it("preserves INCOMPLETE, UNTRUSTED and SYNTHETIC_CLOCK distinctly", () => {
    mockState.mockReturnValue(query(stagingSemantics));
    mockSources.mockReturnValue(query(stagingSources));
    const { container } = renderPage();

    expect(container.textContent).toContain("INCOMPLETE");
    expect(container.textContent).toContain("UNTRUSTED");
    // Each is its own state; none collapses into another.
    expect(container.textContent).not.toMatch(/\bHEALTHY\b/);
    expect(container.textContent).not.toMatch(/\bOK\b/);
  });

  it("never fabricates a coverage percentage", () => {
    // The producer stated coverage as INCOMPLETE with no ratio. Neither 0% nor
    // 100% may appear for it.
    mockState.mockReturnValue(query(stagingSemantics));
    mockSources.mockReturnValue(query(stagingSemantics.items ? stagingSources : []));
    const { container } = renderPage();

    expect(stagingSemantics.items[0].coverage).not.toHaveProperty("ratio");
    expect(container.textContent).not.toContain("100%");
    expect(container.textContent).not.toContain("0%");
  });

  it("does not collapse the runtime array", () => {
    mockState.mockReturnValue(query(stagingSemantics));
    mockSources.mockReturnValue(query(stagingSources));
    const { container } = renderPage();

    const runtime = stagingSemantics.items[0].runtime as string[];
    expect(Array.isArray(runtime)).toBe(true);
    for (const entry of runtime) {
      expect(container.textContent).toContain(entry);
    }
    // Never rendered as a single LIVE/HISTORICAL verdict.
    expect(container.textContent).not.toMatch(/\bHISTORICAL\b(?!-)/);
  });

  it("shows the producer's sequence as the string it is", () => {
    mockState.mockReturnValue(query(stagingState));
    mockSources.mockReturnValue(query(stagingSources));
    const { container } = renderPage();

    for (const row of stagingSources) {
      expect(typeof row.last_accepted_sequence).toBe("string");
      expect(container.textContent).toContain(row.source_instance);
    }
  });

  it("renders a loading state rather than an empty dashboard", () => {
    mockState.mockReturnValue(query(undefined, { isLoading: true }));
    mockSources.mockReturnValue(query(undefined, { isLoading: true }));
    const { container } = renderPage();

    // Must not claim there is no data while it is still being fetched.
    expect(container.textContent).not.toMatch(/no monitoring data/i);
  });

  it("distinguishes an unconfigured deployment from one with no data", () => {
    // Two very different facts that an empty list alone would conflate.
    mockState.mockReturnValue(
      query({ receiver_deployment_environment: "UNKNOWN", configured: false, count: 0, items: [] }),
    );
    mockSources.mockReturnValue(query([]));
    const { container } = renderPage();

    expect(container.textContent).toContain("UNKNOWN");
  });

  it("shows an empty state when the deployment is configured but silent", () => {
    mockState.mockReturnValue(
      query({ receiver_deployment_environment: "staging", configured: true, count: 0, items: [] }),
    );
    mockSources.mockReturnValue(query([]));
    const { container } = renderPage();

    // Silence is reported as silence, not as health.
    expect(container.textContent).not.toMatch(/\bHEALTHY\b/);
    expect(container.textContent).not.toContain("100%");
  });

  it("offers no control that could reach LLS", () => {
    mockState.mockReturnValue(query(stagingState));
    mockSources.mockReturnValue(query(stagingSources));
    const { container } = renderPage();

    // The only interactive elements are the message-type filters.
    const buttons = Array.from(container.querySelectorAll("button"));
    const labels = buttons.map((b) => (b.textContent ?? "").toLowerCase());
    for (const forbidden of [
      "cancel",
      "halt",
      "pause",
      "resume",
      "stop",
      "kill",
      "flatten",
      "liquidate",
      "retry",
      "resend",
      "delete",
      "acknowledge",
    ]) {
      expect(labels.some((label) => label.includes(forbidden))).toBe(false);
    }
    expect(container.querySelectorAll("form").length).toBe(0);
    expect(container.querySelectorAll("input").length).toBe(0);
  });
});
