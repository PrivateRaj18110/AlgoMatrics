import { describe, expect, it } from "vitest";

import { money, pnlClass, signed, toNumber } from "@/lib/format";

describe("format helpers", () => {
  it("formats money with currency symbol", () => {
    expect(money("1234.5", "INR")).toContain("₹");
    expect(money("1234.5", "USD")).toContain("$");
    expect(money(null)).toBe("—");
    expect(money("not-a-number")).toBe("—");
  });

  it("formats signed values with sign prefix", () => {
    expect(signed(100)).toMatch(/^\+/);
    expect(signed(-100)).toMatch(/^-/);
    expect(signed(0)).not.toMatch(/^[+-]/);
  });

  it("classifies pnl colors", () => {
    expect(pnlClass(50)).toContain("profit");
    expect(pnlClass(-50)).toContain("loss");
    expect(pnlClass(0)).toContain("slate");
  });

  it("coerces to number safely", () => {
    expect(toNumber("42.5")).toBe(42.5);
    expect(toNumber(null)).toBe(0);
    expect(toNumber("garbage")).toBe(0);
  });
});
