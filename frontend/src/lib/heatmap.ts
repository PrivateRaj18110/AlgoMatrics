/**
 * Treemap geometry and the diverging colour scale for the market heat map.
 *
 * Pure functions, no React, no DOM — the layout is the part most worth testing
 * and the part most likely to be wrong, so it lives where a test can reach it
 * without rendering anything.
 *
 * A note on sizing, because it is a data-integrity question rather than a
 * cosmetic one. Area conventionally encodes market capitalisation. The F&O
 * heat map takes it from NSE's own pre-open snapshot; when that field is absent
 * every tile gets weight 1 and the page says so, rather than deriving a weight
 * from price or turnover that a viewer would misread as capitalisation.
 */

export interface TreemapInput {
  key: string;
  /** Relative area. Non-finite and non-positive weights are dropped. */
  weight: number;
}

export interface TreemapTile {
  key: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Area-weighted cell, used only inside the layout. */
interface Cell {
  key: string;
  area: number;
}

/**
 * Worst aspect ratio in a candidate row, per Bruls/Huizing/van Wijk.
 *
 * Lower is squarer. Cells arrive in descending area order, so the first is the
 * largest and the last the smallest.
 */
function worstRatio(row: readonly Cell[], side: number): number {
  if (row.length === 0) return Number.POSITIVE_INFINITY;
  const sum = row.reduce((total, cell) => total + cell.area, 0);
  if (sum <= 0 || side <= 0) return Number.POSITIVE_INFINITY;
  const max = row[0].area;
  const min = row[row.length - 1].area;
  if (min <= 0) return Number.POSITIVE_INFINITY;
  const sumSquared = sum * sum;
  const sideSquared = side * side;
  return Math.max((sideSquared * max) / sumSquared, sumSquared / (sideSquared * min));
}

/**
 * Squarified treemap.
 *
 * Fills `width` x `height` exactly, favouring near-square tiles. With uniform
 * weights this degenerates to an even tiling, which is the correct appearance
 * for "no authoritative weighting exists" — an even grid claims nothing.
 */
export function squarify(
  inputs: readonly TreemapInput[],
  width: number,
  height: number,
): TreemapTile[] {
  if (width <= 0 || height <= 0) return [];
  const usable = inputs.filter((input) => Number.isFinite(input.weight) && input.weight > 0);
  if (usable.length === 0) return [];

  const total = usable.reduce((sum, input) => sum + input.weight, 0);
  const area = width * height;
  const cells: Cell[] = [...usable]
    .sort((a, b) => b.weight - a.weight || a.key.localeCompare(b.key))
    .map((input) => ({ key: input.key, area: (input.weight / total) * area }));

  const tiles: TreemapTile[] = [];
  let x = 0;
  let y = 0;
  let w = width;
  let h = height;

  const place = (row: readonly Cell[]): void => {
    const sum = row.reduce((value, cell) => value + cell.area, 0);
    if (sum <= 0) return;
    if (w >= h) {
      const rowWidth = Math.min(sum / h, w);
      let cursor = y;
      row.forEach((cell, index) => {
        const cellHeight = index === row.length - 1 ? y + h - cursor : (cell.area / sum) * h;
        tiles.push({ key: cell.key, x, y: cursor, w: rowWidth, h: cellHeight });
        cursor += cellHeight;
      });
      x += rowWidth;
      w -= rowWidth;
    } else {
      const rowHeight = Math.min(sum / w, h);
      let cursor = x;
      row.forEach((cell, index) => {
        const cellWidth = index === row.length - 1 ? x + w - cursor : (cell.area / sum) * w;
        tiles.push({ key: cell.key, x: cursor, y, w: cellWidth, h: rowHeight });
        cursor += cellWidth;
      });
      y += rowHeight;
      h -= rowHeight;
    }
  };

  let row: Cell[] = [];
  let index = 0;
  while (index < cells.length) {
    const side = Math.min(w, h);
    const candidate = [...row, cells[index]];
    if (row.length === 0 || worstRatio(candidate, side) <= worstRatio(row, side)) {
      row = candidate;
      index += 1;
    } else {
      place(row);
      row = [];
    }
  }
  place(row);
  return tiles;
}

/**
 * Percentage change beyond which colour stops intensifying.
 *
 * Without a clamp a single 18% mover flattens every other security to visual
 * black, which is precisely when a heat map stops being readable. The number
 * itself is always printed on the tile, so the clamp costs no information.
 */
export const DEFAULT_CLAMP_PCT = 3;

/** Signed intensity in [-1, 1]. Non-finite input is treated as no signal. */
export function changeIntensity(pct: number | null, clamp: number = DEFAULT_CLAMP_PCT): number {
  if (pct === null || !Number.isFinite(pct) || clamp <= 0) return 0;
  return Math.max(-clamp, Math.min(clamp, pct)) / clamp;
}

/**
 * Tile background for a percentage change.
 *
 * A continuous red/neutral/green ramp on a dark ground. `null` — meaning the
 * provider returned no change for this instrument — is **not** rendered as the
 * zero colour: it gets a distinct desaturated blue-grey, and the tile prints the
 * word UNKNOWN. Collapsing "unchanged" and "unknown" into one appearance is the
 * heat-map version of reporting a missing metric as 0.
 */
export function changeColor(pct: number | null, clamp: number = DEFAULT_CLAMP_PCT): string {
  if (pct === null || !Number.isFinite(pct)) return "rgb(51, 59, 74)";
  const intensity = changeIntensity(pct, clamp);
  const magnitude = Math.abs(intensity);
  // Neutral ground, lifted toward red or green as magnitude grows.
  const neutral = { r: 38, g: 43, b: 52 };
  const target = intensity >= 0 ? { r: 22, g: 163, b: 74 } : { r: 220, g: 38, b: 38 };
  const mix = (from: number, to: number) => Math.round(from + (to - from) * magnitude);
  return `rgb(${mix(neutral.r, target.r)}, ${mix(neutral.g, target.g)}, ${mix(neutral.b, target.b)})`;
}

/** Readable text colour for a tile of the given change. */
export function changeTextColor(pct: number | null, clamp: number = DEFAULT_CLAMP_PCT): string {
  if (pct === null || !Number.isFinite(pct)) return "rgb(203, 213, 225)";
  return Math.abs(changeIntensity(pct, clamp)) > 0.55 ? "rgb(255, 255, 255)" : "rgb(226, 232, 240)";
}

/** How much of a tile's label fits, decided from its rendered size in pixels. */
export type LabelDensity = "full" | "compact" | "ticker-only" | "none";

/**
 * Label density for a tile.
 *
 * Thresholds are deliberately generous: an overfilled tile in a dense treemap
 * reads as noise, and the reference aesthetic depends on the grid staying
 * legible rather than on every tile being annotated.
 */
export function labelDensity(w: number, h: number): LabelDensity {
  if (w < 26 || h < 16) return "none";
  if (w >= 132 && h >= 72) return "full";
  if (w >= 58 && h >= 34) return "compact";
  return "ticker-only";
}

/** Signed percentage, always with a sign so direction survives a glance. */
export function formatChangePct(pct: number | null): string {
  if (pct === null || !Number.isFinite(pct)) return "UNKNOWN";
  const fixed = pct.toFixed(2);
  return pct > 0 ? `+${fixed}%` : `${fixed}%`;
}
