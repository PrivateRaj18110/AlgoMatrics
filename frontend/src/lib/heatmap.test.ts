/** Treemap geometry and the colour scale. Pure functions, so tested directly. */

import { describe, expect, it } from "vitest";

import {
  changeColor,
  changeIntensity,
  DEFAULT_CLAMP_PCT,
  formatChangePct,
  labelDensity,
  squarify,
} from "@/lib/heatmap";

const uniform = (count: number) =>
  Array.from({ length: count }, (_, index) => ({ key: `S${index}`, weight: 1 }));

describe("squarified treemap", () => {
  it("emits one tile per input", () => {
    expect(squarify(uniform(17), 1600, 900)).toHaveLength(17);
  });

  it("fills the box: total tile area matches the container area", () => {
    const tiles = squarify(uniform(23), 1600, 900);
    const area = tiles.reduce((sum, tile) => sum + tile.w * tile.h, 0);
    expect(area).toBeCloseTo(1600 * 900, 1);
  });

  it("keeps every tile inside the box", () => {
    for (const tile of squarify(uniform(31), 1200, 700)) {
      expect(tile.x).toBeGreaterThanOrEqual(-1e-6);
      expect(tile.y).toBeGreaterThanOrEqual(-1e-6);
      expect(tile.x + tile.w).toBeLessThanOrEqual(1200 + 1e-6);
      expect(tile.y + tile.h).toBeLessThanOrEqual(700 + 1e-6);
    }
  });

  it("gives a heavier input a larger area", () => {
    const tiles = squarify(
      [
        { key: "BIG", weight: 10 },
        { key: "SMALL", weight: 1 },
      ],
      400,
      400,
    );
    const big = tiles.find((tile) => tile.key === "BIG")!;
    const small = tiles.find((tile) => tile.key === "SMALL")!;
    expect(big.w * big.h).toBeGreaterThan(small.w * small.h);
  });

  it("produces equal areas for uniform weights, which is what 'no sizing data' must look like", () => {
    const tiles = squarify(uniform(9), 900, 900);
    const areas = tiles.map((tile) => tile.w * tile.h);
    for (const area of areas) expect(area).toBeCloseTo(areas[0], 4);
  });

  it("drops non-positive and non-finite weights rather than producing degenerate tiles", () => {
    const tiles = squarify(
      [
        { key: "OK", weight: 1 },
        { key: "ZERO", weight: 0 },
        { key: "NEG", weight: -4 },
        { key: "NAN", weight: Number.NaN },
      ],
      100,
      100,
    );
    expect(tiles.map((tile) => tile.key)).toEqual(["OK"]);
  });

  it("returns nothing for an empty universe or a zero-sized box", () => {
    expect(squarify([], 800, 600)).toEqual([]);
    expect(squarify(uniform(4), 0, 600)).toEqual([]);
    expect(squarify(uniform(4), 800, 0)).toEqual([]);
  });

  it("handles a single security by filling the whole box", () => {
    const [tile] = squarify(uniform(1), 500, 300);
    expect(tile.w).toBeCloseTo(500);
    expect(tile.h).toBeCloseTo(300);
  });

  it("is deterministic for equal weights, so tiles do not reshuffle between refreshes", () => {
    const first = squarify(uniform(12), 1600, 900);
    const second = squarify(uniform(12), 1600, 900);
    expect(second).toEqual(first);
  });
});

describe("diverging colour scale", () => {
  it("separates positive, negative and near-zero movers", () => {
    expect(changeIntensity(2)).toBeGreaterThan(0);
    expect(changeIntensity(-2)).toBeLessThan(0);
    expect(changeIntensity(0)).toBe(0);
  });

  it("bounds intensity so one extreme mover cannot flatten the rest", () => {
    expect(changeIntensity(DEFAULT_CLAMP_PCT)).toBe(1);
    expect(changeIntensity(40)).toBe(1);
    expect(changeIntensity(-40)).toBe(-1);
    expect(changeColor(40)).toBe(changeColor(DEFAULT_CLAMP_PCT));
  });

  it("scales magnitude continuously rather than by category", () => {
    expect(changeIntensity(1)).toBeCloseTo(1 / DEFAULT_CLAMP_PCT);
    expect(changeIntensity(2)).toBeGreaterThan(changeIntensity(1));
  });

  it("gives a missing change a colour distinct from an unchanged one", () => {
    // Collapsing "unknown" into the zero colour is the visual form of reporting
    // a missing metric as 0.
    expect(changeColor(null)).not.toBe(changeColor(0));
    expect(changeIntensity(null)).toBe(0);
  });

  it("gives gainers and losers visibly different colours", () => {
    expect(changeColor(2)).not.toBe(changeColor(-2));
  });
});

describe("labels", () => {
  it("shows progressively less on smaller tiles and nothing on unreadable ones", () => {
    expect(labelDensity(300, 200)).toBe("full");
    expect(labelDensity(80, 40)).toBe("compact");
    expect(labelDensity(40, 24)).toBe("ticker-only");
    expect(labelDensity(10, 8)).toBe("none");
  });

  it("always signs a percentage so direction survives a glance", () => {
    expect(formatChangePct(1.25)).toBe("+1.25%");
    expect(formatChangePct(-1.25)).toBe("-1.25%");
    expect(formatChangePct(0)).toBe("0.00%");
  });

  it("prints UNKNOWN for a missing change rather than 0.00%", () => {
    expect(formatChangePct(null)).toBe("UNKNOWN");
    expect(formatChangePct(Number.NaN)).toBe("UNKNOWN");
    expect(formatChangePct(null)).not.toBe("0.00%");
  });
});
