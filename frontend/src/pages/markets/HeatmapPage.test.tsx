import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => ({ useMarketQuotes: vi.fn() }));
vi.mock("@/lib/hooks", () => hooks);

import { HeatmapPage } from "@/pages/markets/HeatmapPage";
import type { MarketInfo } from "@/types/api";

function quote(overrides: Partial<MarketInfo> & { symbol: string }): MarketInfo {
  // Spread last: an explicit `null` override (the case several of these tests
  // exist to cover) must survive, which `??` defaulting would quietly discard.
  return {
    name: `${overrides.symbol} Limited`,
    yahoo_symbol: `${overrides.symbol}.NS`,
    price: "100.00",
    previous_close: "99.00",
    change: "1.00",
    change_pct: "1.01",
    currency: "INR",
    as_of: "2026-09-13T09:45:00Z",
    ...overrides,
  };
}

function result(data: MarketInfo[] | undefined, over: Partial<Record<string, unknown>> = {}) {
  return {
    data,
    isLoading: false,
    isError: false,
    isSuccess: data !== undefined,
    dataUpdatedAt: data !== undefined ? 1_757_760_000_000 : 0,
    ...over,
  };
}

/** Every tile is a button; the page's only other buttons would be controls. */
function tiles() {
  return screen
    .queryAllByRole("button")
    .filter((node) => node.getAttribute("aria-label")?.includes(","));
}

describe("market heatmap", () => {
  beforeEach(() => {
    hooks.useMarketQuotes.mockReset();
  });

  it("renders a positive mover with a signed percentage and a gain colour", () => {
    hooks.useMarketQuotes.mockReturnValue(result([quote({ symbol: "RELIANCE", change_pct: "2.40" })]));
    render(<HeatmapPage />);

    const tile = screen.getByRole("button", { name: /RELIANCE, \+2\.40%/ });
    expect(within(tile).getByText("+2.40%")).toBeInTheDocument();
    // Green channel lifted above the neutral ground.
    expect(tile.style.background).toMatch(/rgb\((\d+), (\d+), (\d+)\)/);
    const [, r, g] = tile.style.background.match(/rgb\((\d+), (\d+), (\d+)\)/)!;
    expect(Number(g)).toBeGreaterThan(Number(r));
  });

  it("renders a negative mover distinctly from a positive one", () => {
    hooks.useMarketQuotes.mockReturnValue(
      result([quote({ symbol: "TCS", change_pct: "-1.80" }), quote({ symbol: "INFY", change_pct: "1.80" })]),
    );
    render(<HeatmapPage />);

    const loser = screen.getByRole("button", { name: /TCS, -1\.80%/ });
    const winner = screen.getByRole("button", { name: /INFY, \+1\.80%/ });
    expect(loser.style.background).not.toBe(winner.style.background);
    const [, lr, lg] = loser.style.background.match(/rgb\((\d+), (\d+), (\d+)\)/)!;
    expect(Number(lr)).toBeGreaterThan(Number(lg));
  });

  it("renders a near-zero mover neutrally but still prints the number", () => {
    hooks.useMarketQuotes.mockReturnValue(result([quote({ symbol: "ITC", change_pct: "0.00" })]));
    render(<HeatmapPage />);

    const tile = screen.getByRole("button", { name: /ITC, 0\.00%/ });
    expect(within(tile).getByText("0.00%")).toBeInTheDocument();
    expect(within(tile).queryByText("UNKNOWN")).not.toBeInTheDocument();
  });

  it("shows UNKNOWN — never 0% — when the provider returned no percentage", () => {
    hooks.useMarketQuotes.mockReturnValue(
      result([quote({ symbol: "WIPRO", change_pct: null }), quote({ symbol: "ITC", change_pct: "0.00" })]),
    );
    render(<HeatmapPage />);

    const missing = screen.getByRole("button", { name: /WIPRO, UNKNOWN/ });
    expect(within(missing).getByText("UNKNOWN")).toBeInTheDocument();
    expect(within(missing).queryByText("0.00%")).not.toBeInTheDocument();

    // And it must not look like the genuinely-unchanged security beside it.
    const unchanged = screen.getByRole("button", { name: /ITC, 0\.00%/ });
    expect(missing.style.background).not.toBe(unchanged.style.background);
    expect(screen.getByText(/marked UNKNOWN, not 0%/)).toBeInTheDocument();
  });

  it("reports the provider's own as_of rather than the time of the fetch", () => {
    hooks.useMarketQuotes.mockReturnValue(
      result([quote({ symbol: "SBIN", as_of: "2026-09-13T09:45:00Z" })]),
    );
    render(<HeatmapPage />);

    // "DATA AS OF" is the source's stamp; "FETCHED" is ours. They are separate
    // readouts on purpose — conflating them is how a stale board looks live.
    expect(screen.getByText("DATA AS OF")).toBeInTheDocument();
    expect(screen.getByText("FETCHED")).toBeInTheDocument();
  });

  it("shows UNKNOWN for as_of when the provider stamped no time", () => {
    hooks.useMarketQuotes.mockReturnValue(result([quote({ symbol: "SBIN", as_of: null })]));
    render(<HeatmapPage />);

    const asOfTerm = screen.getByText("DATA AS OF");
    expect(asOfTerm.nextElementSibling).toHaveTextContent("UNKNOWN");
  });

  it("states that sector classification is unavailable instead of inventing sectors", () => {
    hooks.useMarketQuotes.mockReturnValue(result([quote({ symbol: "LT" })]));
    render(<HeatmapPage />);

    expect(screen.getByText(/SECTOR GROUPING = UNAVAILABLE/)).toBeInTheDocument();
    expect(screen.getByText(/BACKEND DATA SOURCE REQUIRED/)).toBeInTheDocument();
    // None of the reference screenshot's sector names may appear as data.
    expect(screen.queryByText(/ELECTRONIC TECHNOLOGY/)).not.toBeInTheDocument();
    expect(screen.queryByText(/HEALTH TECHNOLOGY/)).not.toBeInTheDocument();
  });

  it("states that tile area is uniform because no sizing field exists", () => {
    hooks.useMarketQuotes.mockReturnValue(result([quote({ symbol: "LT" })]));
    render(<HeatmapPage />);
    expect(screen.getByText(/TILE AREA = UNIFORM/)).toBeInTheDocument();
  });

  it("drops secondary labels on small tiles rather than overcrowding them", () => {
    const many = Array.from({ length: 200 }, (_, index) =>
      quote({ symbol: `SYM${index}`, name: `Company ${index}` }),
    );
    hooks.useMarketQuotes.mockReturnValue(result(many));
    render(<HeatmapPage />);

    expect(tiles()).toHaveLength(200);
    // The ticker survives; the company name is the first thing dropped.
    expect(screen.getByText("SYM0")).toBeInTheDocument();
    expect(screen.queryByText("Company 0")).not.toBeInTheDocument();
  });

  it("shows the company name on a large tile", () => {
    hooks.useMarketQuotes.mockReturnValue(
      result([quote({ symbol: "HDFCBANK", name: "HDFC Bank Limited" })]),
    );
    render(<HeatmapPage />);
    expect(screen.getByText("HDFC Bank Limited")).toBeInTheDocument();
  });

  it("exposes only values the backend actually provides in the tile detail", async () => {
    hooks.useMarketQuotes.mockReturnValue(
      result([quote({ symbol: "AXISBANK", price: "1120.50", previous_close: "1100.00" })]),
    );
    const { container } = render(<HeatmapPage />);

    const tile = screen.getByRole("button", { name: /AXISBANK/ });
    expect(tile.title).toContain("Sector: UNKNOWN");
    expect(tile.title).toContain("Weight: UNIFORM");
    expect(tile.title).toContain("/market-info/quotes");

    await userEvent.click(tile);
    const footer = container.querySelector("footer")!;
    expect(within(footer).getByText("1120.50 INR")).toBeInTheDocument();
    expect(within(footer).getByText("1100.00")).toBeInTheDocument();
    expect(within(footer).getByText("UNIFORM")).toBeInTheDocument();
  });

  it("shows an explicit empty state rather than placeholder instruments", () => {
    hooks.useMarketQuotes.mockReturnValue(result([]));
    render(<HeatmapPage />);

    expect(screen.getByText("NO SECURITIES IN UNIVERSE")).toBeInTheDocument();
    expect(tiles()).toHaveLength(0);
  });

  it("says the data is unavailable on API failure and shows no values", () => {
    hooks.useMarketQuotes.mockReturnValue(
      result(undefined, { isError: true, isSuccess: false, data: undefined }),
    );
    render(<HeatmapPage />);

    expect(screen.getByText("MARKET DATA UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText(/FAILED — SHOWING LAST KNOWN/)).toBeInTheDocument();
    expect(tiles()).toHaveLength(0);
  });

  it("recovers when the API comes back", () => {
    hooks.useMarketQuotes.mockReturnValue(
      result(undefined, { isError: true, isSuccess: false, data: undefined }),
    );
    const view = render(<HeatmapPage />);
    expect(screen.getByText("MARKET DATA UNAVAILABLE")).toBeInTheDocument();

    hooks.useMarketQuotes.mockReturnValue(result([quote({ symbol: "MARUTI", change_pct: "0.90" })]));
    view.rerender(<HeatmapPage />);

    expect(screen.queryByText("MARKET DATA UNAVAILABLE")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MARUTI, \+0\.90%/ })).toBeInTheDocument();
  });

  it("lays tiles out in percentages so the grid rescales with the viewport", () => {
    hooks.useMarketQuotes.mockReturnValue(
      result([quote({ symbol: "A" }), quote({ symbol: "B" }), quote({ symbol: "C" })]),
    );
    render(<HeatmapPage />);

    for (const tile of tiles()) {
      expect(tile.style.width).toMatch(/%$/);
      expect(tile.style.height).toMatch(/%$/);
      expect(tile.style.left).toMatch(/%$/);
      expect(tile.style.top).toMatch(/%$/);
    }
  });

  it("offers no trading control of any kind", () => {
    hooks.useMarketQuotes.mockReturnValue(
      result([quote({ symbol: "RELIANCE" }), quote({ symbol: "TCS" })]),
    );
    const { container } = render(<HeatmapPage />);

    for (const word of [/\bbuy\b/i, /\bsell\b/i, /\border\b/i, /\bexecute\b/i, /square off/i]) {
      expect(container.textContent).not.toMatch(word);
    }
    expect(container.querySelector("form")).toBeNull();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    // Every button on the page is a tile, i.e. selection only.
    expect(screen.queryAllByRole("button")).toHaveLength(tiles().length);
  });
});
