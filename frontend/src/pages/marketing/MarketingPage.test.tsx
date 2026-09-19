import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { MarketingPage } from "@/pages/marketing/MarketingPage";

describe("MarketingPage", () => {
  it("presents the quantitative platform without public signup or performance claims", () => {
    render(
      <MemoryRouter>
        <MarketingPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: /Quantitative Intelligence/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Login" })[0]).toHaveAttribute("href", "/login");
    expect(screen.getAllByRole("link", { name: "Launch Platform" })[0]).toHaveAttribute(
      "href",
      "/login",
    );
    expect(screen.getByRole("link", { name: "Explore Platform" })).toHaveAttribute(
      "href",
      "#platform",
    );
    expect(screen.getByRole("heading", { name: "Security by Design." })).toBeInTheDocument();
    expect(screen.getAllByText("PAPER").length).toBeGreaterThan(0);
    expect(screen.getAllByText("LIVE").length).toBeGreaterThan(0);
    expect(screen.queryByText("Create an account")).not.toBeInTheDocument();
    expect(screen.queryByText(/guaranteed/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("ILLUSTRATIVE").length).toBeGreaterThan(0);
  });
});
