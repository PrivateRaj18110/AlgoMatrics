/**
 * Market heat map — a dense treemap of the platform's market universe.
 *
 * Read-only. There is no order entry, no strategy control and no broker action
 * anywhere on this page, and a test asserts that.
 *
 * Two honesty constraints shape what you see, and both are stated on the page
 * itself rather than buried here:
 *
 * 1. **Universe.** This platform's market data is NSE India, served by
 *    `/market-info/quotes` from the Yahoo provider. It is not the S&P 100, and
 *    the endpoint caps the default universe at 25 active NSE equities. Inventing
 *    constituents to fill the grid would be fabricating market data.
 * 2. **Sizing and sector.** Neither a capitalisation/weight field nor a sector
 *    classification exists anywhere in the backend. Tiles are therefore uniform
 *    and ungrouped, labelled as such. See `@/lib/heatmap` for why a synthesised
 *    weight was rejected.
 *
 * Freshness is reported, never computed. `as_of` is the provider's own market
 * timestamp and is printed verbatim; whether the market is open comes from the
 * platform's existing NSE session calendar. Nothing here evaluates a staleness
 * horizon of its own invention.
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  changeColor,
  changeTextColor,
  DEFAULT_CLAMP_PCT,
  formatChangePct,
  labelDensity,
  squarify,
  type TreemapTile,
} from "@/lib/heatmap";
import { useMarketQuotes } from "@/lib/hooks";
import { getIndianMarketDaySchedule } from "@/lib/marketSessions";
import { clockLabel, dateTimeLabel, latestInstant } from "@/lib/wallboard";
import type { MarketInfo } from "@/types/api";

/** Layout box used before the container has been measured. 16:9, wallboard-ish. */
const FALLBACK_BOX = { width: 1600, height: 900 };

interface Security {
  symbol: string;
  name: string;
  changePct: number | null;
  price: string | null;
  previousClose: string | null;
  currency: string;
  asOf: string | null;
}

function toNumberOrNull(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const amount = Number.parseFloat(value);
  return Number.isFinite(amount) ? amount : null;
}

function toSecurity(row: MarketInfo): Security {
  return {
    symbol: row.symbol,
    name: row.name,
    changePct: toNumberOrNull(row.change_pct),
    price: row.price,
    previousClose: row.previous_close,
    currency: row.currency,
    asOf: row.as_of,
  };
}

/** Measures a container, falling back to a fixed box when measurement is absent. */
function useMeasuredBox(ref: React.RefObject<HTMLElement | null>) {
  const [box, setBox] = useState(FALLBACK_BOX);

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setBox({ width, height });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);

  return box;
}

function marketStatusLabel(now: Date): { label: string; tone: string } {
  const schedule = getIndianMarketDaySchedule(now);
  if (schedule.type === "open") return { label: "NSE SCHEDULED TRADING DAY", tone: "text-emerald-300" };
  if (schedule.type === "weekend") return { label: "NSE CLOSED — WEEKEND", tone: "text-slate-400" };
  return { label: `NSE — ${schedule.reason.toUpperCase()}`, tone: "text-amber-300" };
}

function Tile({
  tile,
  security,
  box,
  selected,
  onSelect,
}: {
  tile: TreemapTile;
  security: Security;
  box: { width: number; height: number };
  selected: boolean;
  onSelect: (symbol: string) => void;
}) {
  const density = labelDensity(tile.w, tile.h);
  const background = changeColor(security.changePct);
  const color = changeTextColor(security.changePct);
  const unknownChange = security.changePct === null;

  const detail = [
    security.symbol,
    security.name,
    `Change: ${formatChangePct(security.changePct)}`,
    `Price: ${security.price ?? "UNKNOWN"} ${security.currency}`,
    `Previous close: ${security.previousClose ?? "UNKNOWN"}`,
    "Sector: UNKNOWN (not provided by the platform)",
    "Weight: UNIFORM (no sizing field available)",
    "Source: /market-info/quotes (Yahoo, delayed)",
    `As of: ${dateTimeLabel(security.asOf)}`,
  ].join("\n");

  return (
    <button
      type="button"
      onClick={() => onSelect(security.symbol)}
      title={detail}
      aria-label={`${security.symbol}, ${formatChangePct(security.changePct)}`}
      style={{
        position: "absolute",
        left: `${(tile.x / box.width) * 100}%`,
        top: `${(tile.y / box.height) * 100}%`,
        width: `${(tile.w / box.width) * 100}%`,
        height: `${(tile.h / box.height) * 100}%`,
        background,
        color,
      }}
      className={
        "flex flex-col items-center justify-center overflow-hidden border text-center leading-none " +
        "focus:z-10 focus:outline-2 focus:outline-offset-[-2px] focus:outline-sky-300 " +
        (selected ? "border-sky-300 z-10" : "border-slate-900/70") +
        (unknownChange ? " [background-image:repeating-linear-gradient(45deg,transparent,transparent_5px,rgba(148,163,184,0.18)_5px,rgba(148,163,184,0.18)_10px)]" : "")
      }
    >
      {density === "none" ? null : (
        <>
          <span className="font-mono text-[clamp(9px,1.1vw,15px)] font-bold tracking-tight">
            {security.symbol}
          </span>
          {density === "full" ? (
            <span className="mt-0.5 max-w-full truncate px-1 font-sans text-[clamp(8px,0.7vw,11px)] opacity-75">
              {security.name}
            </span>
          ) : null}
          {density === "full" || density === "compact" ? (
            <span className="mt-0.5 font-mono text-[clamp(8px,0.9vw,13px)] font-semibold">
              {formatChangePct(security.changePct)}
            </span>
          ) : null}
        </>
      )}
    </button>
  );
}

export function HeatmapPage() {
  const quotes = useMarketQuotes();
  const containerRef = useRef<HTMLDivElement>(null);
  const box = useMeasuredBox(containerRef);
  const [selected, setSelected] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());

  // One timer, cleared on unmount. Drives only the wall-clock readout — never a
  // freshness verdict, which would be a horizon this contract does not define.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const securities = useMemo<Security[]>(
    () => (quotes.data ?? []).map(toSecurity),
    [quotes.data],
  );

  const tiles = useMemo(
    () =>
      squarify(
        securities.map((security) => ({ key: security.symbol, weight: 1 })),
        box.width,
        box.height,
      ),
    [securities, box.width, box.height],
  );

  const byFirstSymbol = useMemo(() => {
    const index = new Map<string, Security>();
    securities.forEach((security) => index.set(security.symbol, security));
    return index;
  }, [securities]);

  const asOf = latestInstant(securities.map((security) => security.asOf));
  const market = marketStatusLabel(now);
  const selectedSecurity = selected ? (byFirstSymbol.get(selected) ?? null) : null;
  const unknownCount = securities.filter((security) => security.changePct === null).length;

  return (
    <div className="flex h-[calc(100dvh-7rem)] min-h-[28rem] flex-col gap-2 rounded-xl bg-[#0b0f16] p-3 text-slate-200">
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <div className="flex items-baseline gap-3">
          <h1 className="font-mono text-base font-bold tracking-[0.2em] text-slate-100">
            MARKET HEATMAP
          </h1>
          <span className="font-mono text-[11px] tracking-wider text-slate-400">
            NSE EQUITIES · PLATFORM UNIVERSE
          </span>
        </div>
        <dl className="flex flex-wrap items-baseline gap-x-5 gap-y-1 font-mono text-[11px]">
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">MARKET</dt>
            <dd className={market.tone}>{market.label}</dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">DATA AS OF</dt>
            <dd className="text-slate-200">
              {asOf.state === "UNKNOWN" ? "UNKNOWN" : dateTimeLabel(asOf.value)}
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">FETCHED</dt>
            <dd className="text-slate-200">
              {quotes.isError
                ? "FAILED — SHOWING LAST KNOWN"
                : quotes.dataUpdatedAt
                  ? clockLabel(new Date(quotes.dataUpdatedAt).toISOString())
                  : "UNKNOWN"}
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">SECURITIES</dt>
            <dd className="text-slate-200">{securities.length}</dd>
          </div>
        </dl>
      </header>

      {/* Stated on the page, not only in the code: two encodings a heat map
          normally carries are absent from this platform's data. */}
      <p className="font-mono text-[10px] leading-relaxed tracking-wide text-amber-300/80">
        TILE AREA = UNIFORM — no market-cap, index-weight or other authoritative sizing field exists
        in this platform. SECTOR GROUPING = UNAVAILABLE — instruments carry no sector classification.
        Both are BACKEND DATA SOURCE REQUIRED; neither has been synthesised.
        {unknownCount > 0 ? ` ${unknownCount} security(s) report no change and are marked UNKNOWN, not 0%.` : ""}
      </p>

      <div
        ref={containerRef}
        className="relative min-h-0 flex-1 overflow-hidden rounded-lg bg-[#05070b] ring-1 ring-slate-800"
      >
        {quotes.isLoading ? (
          <p className="absolute inset-0 flex items-center justify-center font-mono text-xs text-slate-500">
            LOADING MARKET UNIVERSE…
          </p>
        ) : null}

        {!quotes.isLoading && securities.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="font-mono text-sm tracking-widest text-slate-300">
              {quotes.isError ? "MARKET DATA UNAVAILABLE" : "NO SECURITIES IN UNIVERSE"}
            </p>
            <p className="max-w-lg font-mono text-[11px] leading-relaxed text-slate-500">
              {quotes.isError
                ? "The market-info request failed. No values are shown, because there are no previously known values to mark as stale."
                : "The platform reports no active NSE equities. Nothing is displayed rather than filling the grid with placeholder instruments."}
            </p>
          </div>
        ) : null}

        {tiles.map((tile) => {
          const security = byFirstSymbol.get(tile.key);
          if (!security) return null;
          return (
            <Tile
              key={tile.key}
              tile={tile}
              security={security}
              box={box}
              selected={selected === tile.key}
              onSelect={setSelected}
            />
          );
        })}
      </div>

      <footer className="flex min-h-[2.25rem] flex-wrap items-center gap-x-6 gap-y-1 rounded-lg bg-[#05070b] px-3 py-1.5 font-mono text-[11px] ring-1 ring-slate-800">
        {selectedSecurity ? (
          <>
            <span className="font-bold tracking-wider text-slate-100">{selectedSecurity.symbol}</span>
            <span className="truncate text-slate-400">{selectedSecurity.name}</span>
            <span className="text-slate-500">
              CHANGE{" "}
              <span className="text-slate-100">{formatChangePct(selectedSecurity.changePct)}</span>
            </span>
            <span className="text-slate-500">
              PRICE{" "}
              <span className="text-slate-100">
                {selectedSecurity.price ?? "UNKNOWN"} {selectedSecurity.currency}
              </span>
            </span>
            <span className="text-slate-500">
              PREV CLOSE{" "}
              <span className="text-slate-100">{selectedSecurity.previousClose ?? "UNKNOWN"}</span>
            </span>
            <span className="text-slate-500">
              SECTOR <span className="text-amber-300">UNKNOWN</span>
            </span>
            <span className="text-slate-500">
              WEIGHT <span className="text-amber-300">UNIFORM</span>
            </span>
            <span className="text-slate-500">
              AS OF <span className="text-slate-100">{dateTimeLabel(selectedSecurity.asOf)}</span>
            </span>
          </>
        ) : (
          <span className="text-slate-500">
            SELECT A TILE FOR DETAIL · COLOUR = % CHANGE, INTENSITY CLAMPED AT ±{DEFAULT_CLAMP_PCT}%
            SO ONE EXTREME MOVER DOES NOT FLATTEN THE GRID · HATCHED = UNKNOWN
          </span>
        )}
      </footer>
    </div>
  );
}
