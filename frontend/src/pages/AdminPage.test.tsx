import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/hooks", () => ({
  useAdminVenueInstruments: () => ({ data: [], isLoading: false }),
  useBrokerCatalog: () => ({ data: [] }),
  useInstruments: () => ({ data: [] }),
}));

import { AdminPage } from "@/pages/AdminPage";

describe("AdminPage venue mappings", () => {
  it("shows the fail-closed empty state and add action", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/app/admin/venue-instruments"]}>
          <Routes>
            <Route path="/app/admin/:section" element={<AdminPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("No venue mappings")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add mapping" })).toBeInTheDocument();
  });
});
