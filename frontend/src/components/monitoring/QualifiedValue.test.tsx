import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QualifiedValue } from "./QualifiedValue";
import {
  CoverageBadge,
  EnvironmentBadge,
  FreshnessBadge,
  RuntimeBadges,
  TrustBadge,
} from "./FreshnessBadge";

describe("QualifiedValue", () => {
  it("renders an observed value as the value itself", () => {
    render(<QualifiedValue value={{ status: "OBSERVED", value: 21 }} />);
    expect(screen.getByText("21")).toBeInTheDocument();
    expect(screen.queryByText("OBSERVED")).not.toBeInTheDocument();
  });

  it("renders UNKNOWN as the word UNKNOWN, never as zero or a dash", () => {
    // The single most important assertion in the frontend suite.
    render(<QualifiedValue value={{ status: "UNKNOWN", value: null, reason: "not_available" }} />);
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
    expect(screen.queryByText("null")).not.toBeInTheDocument();
  });

  it("does not render an explicit null as a value", () => {
    const { container } = render(<QualifiedValue value={{ status: "UNKNOWN", value: null }} />);
    expect(container.textContent).not.toMatch(/\d/);
    expect(container.textContent).toContain("UNKNOWN");
  });

  it("keeps a value visible alongside a STALE marker", () => {
    render(<QualifiedValue value={{ status: "STALE", value: 100 }} />);
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("STALE")).toBeInTheDocument();
  });

  it.each([
    ["UNTRUSTED", 4.2],
    ["SIMULATED", 7],
  ])("shows %s beside its value", (status, value) => {
    render(<QualifiedValue value={{ status, value }} />);
    expect(screen.getByText(String(value))).toBeInTheDocument();
    expect(screen.getByText(status)).toBeInTheDocument();
  });

  it.each(["UNSUPPORTED", "NOT_APPLICABLE", "INCOMPLETE"])(
    "shows %s with no fabricated value",
    (status) => {
      const { container } = render(<QualifiedValue value={{ status }} />);
      expect(container.textContent).not.toMatch(/\d/);
    },
  );

  it("shows an unfamiliar status unmodified rather than assuming health", () => {
    render(<QualifiedValue value={{ status: "SOMETHING_NEW", value: 5 }} />);
    expect(screen.getByText("SOMETHING_NEW")).toBeInTheDocument();
  });

  it("flags a bare scalar rather than displaying it as a fact", () => {
    render(<QualifiedValue value={100} />);
    expect(screen.getByText("UNQUALIFIED")).toBeInTheDocument();
  });
});

describe("FreshnessBadge", () => {
  it("shows the source's asserted state and the time the source derived it", () => {
    render(
      <FreshnessBadge
        freshness={{ source: "STALE", derived_at: "2026-09-11T09:01:34Z", reason: "r" }}
      />,
    );
    expect(screen.getByText("STALE")).toBeInTheDocument();
    expect(screen.getByText(/SOURCE DERIVED: 2026-09-11 09:01:34Z/)).toBeInTheDocument();
  });

  it("does not upgrade STALE no matter when the page rendered", () => {
    // There is no timer and no clock arithmetic; rendering now cannot change it.
    render(<FreshnessBadge freshness={{ source: "STALE", derived_at: "2020-01-01T00:00:00Z" }} />);
    expect(screen.getByText("STALE")).toBeInTheDocument();
    expect(screen.queryByText("FRESH")).not.toBeInTheDocument();
    expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
  });

  it("says so when the source stated no freshness", () => {
    render(<FreshnessBadge freshness={{}} />);
    expect(screen.getByText("FRESHNESS NOT STATED")).toBeInTheDocument();
  });

  it("marks an unrecognised state as unrecognised", () => {
    render(<FreshnessBadge freshness={{ source: "SOMETHING_NEW" }} />);
    expect(screen.getByText("SOMETHING_NEW")).toBeInTheDocument();
    expect(screen.getByText(/unrecognised state/)).toBeInTheDocument();
  });
});

describe("environment, runtime, trust and coverage", () => {
  it.each(["offline_fixture", "replay", "live_market_paper", "broker_sandbox"])(
    "marks %s distinctly from live trading",
    (environment) => {
      render(<EnvironmentBadge sourceEnvironment={environment} />);
      expect(screen.getByText(environment)).toBeInTheDocument();
    },
  );

  it("renders runtime as the capture identifiers it is", () => {
    render(<RuntimeBadges runtime={["historical-final/2503001", "other/42"]} />);
    expect(screen.getByText("historical-final/2503001")).toBeInTheDocument();
    expect(screen.getByText("other/42")).toBeInTheDocument();
    // Never collapsed into a classification the source did not send.
    expect(screen.queryByText("HISTORICAL")).not.toBeInTheDocument();
    expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
  });

  it("says when no capture was reported", () => {
    render(<RuntimeBadges runtime={[]} />);
    expect(screen.getByText("NO CAPTURE REPORTED")).toBeInTheDocument();
  });

  it("preserves an UNTRUSTED trust status", () => {
    render(<TrustBadge trust={{ status: "UNTRUSTED" }} />);
    expect(screen.getByText("UNTRUSTED")).toBeInTheDocument();
  });

  it("says TRUST NOT STATED when the source stated none", () => {
    render(<TrustBadge trust={{}} />);
    expect(screen.getByText("TRUST NOT STATED")).toBeInTheDocument();
  });

  it("shows coverage as the source stated it, with no percentage invented", () => {
    const { container } = render(
      <CoverageBadge coverage={{ status: "INCOMPLETE", capture_status: "salvaged" }} />,
    );
    expect(screen.getByText("INCOMPLETE")).toBeInTheDocument();
    expect(screen.getByText("salvaged")).toBeInTheDocument();
    expect(container.textContent).not.toContain("%");
  });

  it("says COVERAGE NOT STATED rather than showing 0% or 100%", () => {
    const { container } = render(<CoverageBadge coverage={{}} />);
    expect(screen.getByText("COVERAGE NOT STATED")).toBeInTheDocument();
    expect(container.textContent).not.toContain("0%");
    expect(container.textContent).not.toContain("100%");
  });
});
