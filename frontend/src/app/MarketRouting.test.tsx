import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { InternationalRootRedirect, InternationalRouteHandler } from "@/app/router";
import { INTERNATIONAL_MARKET_ENABLED, VISIBLE_MARKETS } from "@/lib/marketRegion";

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="current-location">{location.pathname}</div>;
}

describe("Market routing and visibility", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  it("configures India as the only visible market when INTERNATIONAL_MARKET_ENABLED is false", () => {
    expect(INTERNATIONAL_MARKET_ENABLED).toBe(false);
    expect(VISIBLE_MARKETS).toEqual(["india"]);
  });

  it("redirects manual /app/international access to /app/india/overview", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/app/international"]}>
          <Routes>
            <Route path="/app/international" element={<InternationalRootRedirect />} />
            <Route path="/app/india/overview" element={<LocationDisplay />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("current-location")).toHaveTextContent("/app/india/overview");
  });

  it("redirects manual /app/international/:section to corresponding /app/india/:section", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/app/international/positions"]}>
          <Routes>
            <Route path="/app/international/:section" element={<InternationalRouteHandler />} />
            <Route path="/app/india/positions" element={<LocationDisplay />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("current-location")).toHaveTextContent("/app/india/positions");
  });

  it("redirects manual /app/international/closed-trades to /app/india/closed-trades", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/app/international/closed-trades"]}>
          <Routes>
            <Route path="/app/international/:section" element={<InternationalRouteHandler />} />
            <Route path="/app/india/closed-trades" element={<LocationDisplay />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("current-location")).toHaveTextContent("/app/india/closed-trades");
  });

  it("redirects manual /app/international/strategies to /app/india/strategies", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/app/international/strategies"]}>
          <Routes>
            <Route path="/app/international/:section" element={<InternationalRouteHandler />} />
            <Route path="/app/india/strategies" element={<LocationDisplay />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("current-location")).toHaveTextContent("/app/india/strategies");
  });

  it("redirects manual /app/international/system-health to /app/india/system-health", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/app/international/system-health"]}>
          <Routes>
            <Route path="/app/international/:section" element={<InternationalRouteHandler />} />
            <Route path="/app/india/system-health" element={<LocationDisplay />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("current-location")).toHaveTextContent("/app/india/system-health");
  });
});
