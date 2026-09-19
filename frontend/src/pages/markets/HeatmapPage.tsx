/**
 * NSE F&O heat map — every stock in the F&O segment, grouped by sector and
 * sized by market capitalisation.
 *
 * Read-only: no order entry, strategy control or broker action anywhere here,
 * and a test asserts that.
 *
 * Data provenance is stated on the page:
 * - **Universe** — NSE's own F&O list, taken from the pre-open snapshot the
 *   platform stores each trading morning (a built-in list only before the first
 *   snapshot exists, and the header says so).
 * - **Size** — market cap from that same NSE snapshot. When it is missing, tiles
 *   fall back to equal size and the page says so; a size is never invented.
 * - **Colour / numbers** — delayed Yahoo quotes. A missing change is UNKNOWN,
 *   hatched, never 0%.
 */

import { clsx } from "clsx";
import { useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  changeColor,
  changeTextColor,
  DEFAULT_CLAMP_PCT,
  formatChangePct,
  labelDensity,
  squarify,
  type TreemapTile,
} from "@/lib/heatmap";
import { getIndianMarketDaySchedule } from "@/lib/marketSessions";
import {
  compactNumber,
  crore,
  type FoStock,
  pctText,
  price,
  rangePosition,
  toneClass,
  unixToIso,
  useFoHeatmap,
} from "@/lib/markets";
import { clockLabel, dateTimeLabel, latestInstant } from "@/lib/wallboard";

/** Layout box used before the container has been measured. 16:9, wallboard-ish. */
const FALLBACK_BOX = { width: 1600, height: 900 };
const SECTOR_HEADER_PX = 18;

type SizeMode = "cap" | "equal";
type View = "map" | "table";
type SortKey = "symbol" | "sector" | "change_pct" | "price" | "range" | "volume" | "market_cap";

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

interface PlacedTile extends TreemapTile {
  stock: FoStock;
}

interface SectorFrame extends TreemapTile {
  sector: string;
  change: number | null;
}

/** Two-level squarified layout: sectors first, then stocks inside each sector. */
function layout(
  stocks: FoStock[],
  weightOf: (stock: FoStock) => number,
  width: number,
  height: number,
): { frames: SectorFrame[]; tiles: PlacedTile[] } {
  const bySector = new Map<string, FoStock[]>();
  for (const stock of stocks) {
    const members = bySector.get(stock.sector) ?? [];
    members.push(stock);
    bySector.set(stock.sector, members);
  }
  const sectorTiles = squarify(
    [...bySector.entries()].map(([sector, members]) => ({
      key: sector,
      weight: members.reduce((sum, stock) => sum + weightOf(stock), 0),
    })),
    width,
    height,
  );
  const frames: SectorFrame[] = [];
  const tiles: PlacedTile[] = [];
  for (const frame of sectorTiles) {
    const members = bySector.get(frame.key) ?? [];
    const known = members.filter((stock) => stock.change_pct !== null);
    const totalWeight = known.reduce((sum, stock) => sum + weightOf(stock), 0);
    frames.push({
      ...frame,
      sector: frame.key,
      change: totalWeight
        ? known.reduce((sum, stock) => sum + (stock.change_pct ?? 0) * weightOf(stock), 0) /
          totalWeight
        : null,
    });
    const header = frame.h > 48 && frame.w > 70 ? SECTOR_HEADER_PX : 0;
    const bySymbol = new Map(members.map((stock) => [stock.symbol, stock]));
    for (const tile of squarify(
      members.map((stock) => ({ key: stock.symbol, weight: weightOf(stock) })),
      Math.max(frame.w - 2, 1),
      Math.max(frame.h - header - 2, 1),
    )) {
      const stock = bySymbol.get(tile.key);
      if (stock) {
        tiles.push({ ...tile, x: tile.x + frame.x + 1, y: tile.y + frame.y + header + 1, stock });
      }
    }
  }
  return { frames, tiles };
}

function pctBox(tile: TreemapTile, box: { width: number; height: number }): React.CSSProperties {
  return {
    position: "absolute",
    left: `${(tile.x / box.width) * 100}%`,
    top: `${(tile.y / box.height) * 100}%`,
    width: `${(tile.w / box.width) * 100}%`,
    height: `${(tile.h / box.height) * 100}%`,
  };
}

function Tile({
  tile,
  box,
  selected,
  onSelect,
}: {
  tile: PlacedTile;
  box: { width: number; height: number };
  selected: boolean;
  onSelect: (symbol: string) => void;
}) {
  const { stock } = tile;
  const density = labelDensity(tile.w, tile.h);
  const unknownChange = stock.change_pct === null;
  const detail = [
    `${stock.symbol} — ${stock.name}`,
    `Sector: ${stock.sector}`,
    `Change: ${formatChangePct(stock.change_pct)}`,
    `Price: ${price(stock.price)}  (prev close ${price(stock.previous_close)})`,
    `Market cap: ${crore(stock.market_cap)}`,
    `As of: ${dateTimeLabel(unixToIso(stock.as_of))}`,
  ].join("\n");

  return (
    <button
      type="button"
      onClick={() => onSelect(stock.symbol)}
      title={detail}
      aria-label={`${stock.symbol}, ${formatChangePct(stock.change_pct)}`}
      style={{
        ...pctBox(tile, box),
        background: changeColor(stock.change_pct),
        color: changeTextColor(stock.change_pct),
      }}
      className={clsx(
        "flex flex-col items-center justify-center overflow-hidden border text-center leading-none transition-[filter] hover:brightness-125",
        "focus:z-10 focus:outline-2 focus:outline-offset-[-2px] focus:outline-sky-300",
        selected ? "z-10 border-sky-300" : "border-[#05070b]",
        unknownChange &&
          "[background-image:repeating-linear-gradient(45deg,transparent,transparent_5px,rgba(148,163,184,0.18)_5px,rgba(148,163,184,0.18)_10px)]",
      )}
    >
      {density === "none" ? null : (
        <>
          <span className="font-mono text-[clamp(9px,1vw,15px)] font-bold tracking-tight">
            {stock.symbol}
          </span>
          {density === "full" ? (
            <span className="mt-0.5 max-w-full truncate px-1 font-sans text-[clamp(8px,0.65vw,11px)] opacity-75">
              {stock.name}
            </span>
          ) : null}
          {density === "full" || density === "compact" ? (
            <span className="mt-0.5 font-mono text-[clamp(8px,0.85vw,13px)] font-semibold">
              {formatChangePct(stock.change_pct)}
            </span>
          ) : null}
        </>
      )}
    </button>
  );
}

function RangeBar({ stock }: { stock: FoStock }) {
  const position = rangePosition(stock);
  if (position === null) return <span className="text-slate-500">—</span>;
  return (
    <span
      className="relative inline-block h-1.5 w-20 rounded-full bg-slate-700/60"
      title={`52-week range ${price(stock.year_low)} – ${price(stock.year_high)}`}
    >
      <span
        className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent-300 ring-2 ring-[#0b0f16]"
        style={{ left: `${position * 100}%` }}
      />
    </span>
  );
}

const COLUMNS: Array<{ key: SortKey; label: string; numeric?: boolean }> = [
  { key: "symbol", label: "Symbol" },
  { key: "sector", label: "Sector" },
  { key: "price", label: "Price", numeric: true },
  { key: "change_pct", label: "Chg %", numeric: true },
  { key: "range", label: "52W range" },
  { key: "volume", label: "Volume", numeric: true },
  { key: "market_cap", label: "Mkt cap", numeric: true },
];

function sortValue(stock: FoStock, key: SortKey): number | string | null {
  if (key === "range") return rangePosition(stock);
  return stock[key];
}

function StockTable({
  stocks,
  selected,
  onSelect,
}: {
  stocks: FoStock[];
  selected: string | null;
  onSelect: (symbol: string) => void;
}) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "change_pct", desc: true });
  const rows = useMemo(() => {
    const sorted = [...stocks].sort((a, b) => {
      const left = sortValue(a, sort.key);
      const right = sortValue(b, sort.key);
      if (left === null) return 1;
      if (right === null) return -1;
      const order = typeof left === "string" ? left.localeCompare(String(right)) : left - Number(right);
      return sort.desc ? -order : order;
    });
    return sorted;
  }, [stocks, sort]);

  return (
    <div className="min-h-0 flex-1 overflow-auto rounded-lg bg-[#05070b] ring-1 ring-slate-800">
      <table className="w-full min-w-max text-left font-mono text-xs">
        <thead className="sticky top-0 bg-[#0b0f16] text-[10px] tracking-wider text-slate-500 uppercase">
          <tr>
            {COLUMNS.map((column) => (
              <th key={column.key} className={clsx("px-3 py-2 font-medium", column.numeric && "text-right")}>
                <button
                  type="button"
                  onClick={() =>
                    setSort((current) => ({
                      key: column.key,
                      desc: current.key === column.key ? !current.desc : column.numeric === true,
                    }))
                  }
                  className="inline-flex items-center gap-1 hover:text-slate-200"
                >
                  {column.label}
                  {sort.key === column.key ? (sort.desc ? "▾" : "▴") : null}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/70">
          {rows.map((stock) => (
            <tr
              key={stock.symbol}
              onClick={() => onSelect(stock.symbol)}
              className={clsx(
                "cursor-pointer text-slate-300 hover:bg-white/[0.03]",
                selected === stock.symbol && "bg-sky-500/10",
              )}
            >
              <td className="px-3 py-1.5">
                <div className="font-bold text-slate-100">{stock.symbol}</div>
                <div className="max-w-48 truncate font-sans text-[10px] text-slate-500">{stock.name}</div>
              </td>
              <td className="px-3 py-1.5 font-sans text-slate-400">{stock.sector}</td>
              <td className="px-3 py-1.5 text-right">{price(stock.price)}</td>
              <td className={clsx("px-3 py-1.5 text-right font-semibold", toneClass(stock.change_pct))}>
                {pctText(stock.change_pct)}
              </td>
              <td className="px-3 py-1.5">
                <RangeBar stock={stock} />
              </td>
              <td className="px-3 py-1.5 text-right text-slate-400">{compactNumber(stock.volume)}</td>
              <td className="px-3 py-1.5 text-right text-slate-400">{crore(stock.market_cap)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function HeatmapPage() {
  const heatmap = useFoHeatmap();
  const containerRef = useRef<HTMLDivElement>(null);
  const box = useMeasuredBox(containerRef);
  const [selected, setSelected] = useState<string | null>(null);
  const [sector, setSector] = useState<string | null>(null);
  const [view, setView] = useState<View>("map");
  const [sizeMode, setSizeMode] = useState<SizeMode>("cap");
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search.trim().toUpperCase());
  const [now, setNow] = useState(() => new Date());

  // One timer, cleared on unmount. Drives only the wall-clock readout.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const all = useMemo(() => heatmap.data?.stocks ?? [], [heatmap.data]);
  const hasCaps = all.some((stock) => (stock.market_cap ?? 0) > 0);
  const effectiveSize: SizeMode = hasCaps ? sizeMode : "equal";
  const sectors = useMemo(
    () => [...new Set(all.map((stock) => stock.sector))].sort(),
    [all],
  );
  const visible = useMemo(
    () =>
      all.filter(
        (stock) =>
          (!sector || stock.sector === sector) &&
          (!query || stock.symbol.includes(query) || stock.name.toUpperCase().includes(query)),
      ),
    [all, sector, query],
  );

  const { frames, tiles } = useMemo(
    () =>
      layout(
        visible,
        (stock) => (effectiveSize === "cap" ? stock.market_cap || 0 : 1) || 1,
        box.width,
        box.height,
      ),
    [visible, effectiveSize, box.width, box.height],
  );

  const asOf = latestInstant(all.map((stock) => unixToIso(stock.as_of)));
  const market = marketStatusLabel(now);
  const selectedStock = selected ? (all.find((stock) => stock.symbol === selected) ?? null) : null;
  const unknownCount = all.filter((stock) => stock.change_pct === null).length;
  const breadth = heatmap.data?.breadth;
  const universe = heatmap.data?.universe;

  return (
    <div className="flex h-[calc(100dvh-8.5rem)] min-h-[30rem] flex-col gap-2 rounded-2xl bg-[#0b0f16] p-3 text-slate-200 ring-1 ring-white/5">
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <div className="flex items-baseline gap-3">
          <h1 className="font-mono text-base font-bold tracking-[0.2em] text-slate-100">
            F&amp;O HEATMAP
          </h1>
          <span className="font-mono text-[11px] tracking-wider text-slate-400">
            {all.length} NSE F&amp;O STOCKS ·{" "}
            {universe?.source === "nse"
              ? `LIST FROM NSE ${universe.trade_date ?? ""}`
              : "BUILT-IN LIST UNTIL THE FIRST NSE SNAPSHOT"}
          </span>
        </div>
        <dl className="flex flex-wrap items-baseline gap-x-5 gap-y-1 font-mono text-[11px]">
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">MARKET</dt>
            <dd className={market.tone}>{market.label}</dd>
          </div>
          {breadth ? (
            <div className="flex items-baseline gap-1.5">
              <dt className="text-slate-500">A / D</dt>
              <dd>
                <span className="text-emerald-300">{breadth.advances}</span>
                <span className="text-slate-500"> / </span>
                <span className="text-rose-300">{breadth.declines}</span>
              </dd>
            </div>
          ) : null}
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">DATA AS OF</dt>
            <dd className="text-slate-200">
              {asOf.state === "UNKNOWN" ? "UNKNOWN" : dateTimeLabel(asOf.value)}
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">FETCHED</dt>
            <dd className="text-slate-200">
              {heatmap.isError
                ? "FAILED — SHOWING LAST KNOWN"
                : heatmap.dataUpdatedAt
                  ? clockLabel(new Date(heatmap.dataUpdatedAt).toISOString())
                  : "UNKNOWN"}
            </dd>
          </div>
        </dl>
      </header>

      <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
        <div className="inline-flex rounded-md bg-[#05070b] p-0.5 ring-1 ring-slate-800">
          {(["map", "table"] as View[]).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={view === option}
              onClick={() => setView(option)}
              className={clsx(
                "rounded px-2.5 py-1 tracking-wider uppercase",
                view === option ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200",
              )}
            >
              {option}
            </button>
          ))}
        </div>
        {view === "map" && hasCaps ? (
          <div className="inline-flex rounded-md bg-[#05070b] p-0.5 ring-1 ring-slate-800">
            {(
              [
                ["cap", "SIZE: MKT CAP"],
                ["equal", "SIZE: EQUAL"],
              ] as Array<[SizeMode, string]>
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                aria-pressed={sizeMode === mode}
                onClick={() => setSizeMode(mode)}
                className={clsx(
                  "rounded px-2.5 py-1 tracking-wider",
                  sizeMode === mode ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="SEARCH SYMBOL"
          aria-label="Search symbol"
          className="h-7 w-36 rounded-md bg-[#05070b] px-2 text-[11px] tracking-wider text-slate-200 uppercase ring-1 ring-slate-800 placeholder:text-slate-600 focus:ring-sky-400 focus:outline-none"
        />
        <div className="flex flex-wrap gap-1">
          <button
            type="button"
            aria-pressed={sector === null}
            onClick={() => setSector(null)}
            className={clsx(
              "rounded px-2 py-1",
              sector === null ? "bg-sky-500/20 text-sky-200" : "text-slate-500 hover:text-slate-300",
            )}
          >
            ALL SECTORS
          </button>
          {sectors.map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={sector === name}
              onClick={() => setSector(sector === name ? null : name)}
              className={clsx(
                "rounded px-2 py-1 uppercase",
                sector === name ? "bg-sky-500/20 text-sky-200" : "text-slate-500 hover:text-slate-300",
              )}
            >
              {name}
            </button>
          ))}
        </div>
      </div>

      <p className="font-mono text-[10px] leading-relaxed tracking-wide text-slate-500">
        {effectiveSize === "cap"
          ? "TILE AREA = MARKET CAP (NSE PRE-OPEN SNAPSHOT) · GROUPED BY SECTOR"
          : hasCaps
            ? "TILE AREA = EQUAL · GROUPED BY SECTOR"
            : "TILE AREA = EQUAL — MARKET CAP NOT YET AVAILABLE, NOT SYNTHESISED · GROUPED BY SECTOR"}
        {` · COLOUR = % CHANGE, CLAMPED AT ±${DEFAULT_CLAMP_PCT}%`}
        {unknownCount > 0 ? ` · ${unknownCount} WITHOUT A QUOTE ARE HATCHED AND MARKED UNKNOWN, NOT 0%` : ""}
      </p>

      {view === "table" ? (
        <StockTable stocks={visible} selected={selected} onSelect={setSelected} />
      ) : (
        <div
          ref={containerRef}
          className="relative min-h-0 flex-1 overflow-hidden rounded-lg bg-[#05070b] ring-1 ring-slate-800"
        >
          {heatmap.isLoading ? (
            <p className="absolute inset-0 flex items-center justify-center font-mono text-xs text-slate-500">
              LOADING F&amp;O UNIVERSE…
            </p>
          ) : null}
          {!heatmap.isLoading && visible.length === 0 ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center">
              <p className="font-mono text-sm tracking-widest text-slate-300">
                {heatmap.isError
                  ? "MARKET DATA UNAVAILABLE"
                  : all.length === 0
                    ? "NO SECURITIES IN UNIVERSE"
                    : "NOTHING MATCHES THE FILTER"}
              </p>
              <p className="max-w-lg font-mono text-[11px] leading-relaxed text-slate-500">
                {heatmap.isError
                  ? "The market request failed. No values are shown, because there are no previously known values to mark as stale."
                  : "Nothing is displayed rather than filling the grid with placeholder instruments."}
              </p>
            </div>
          ) : null}
          {frames.map((frame) => (
            <div
              key={frame.sector}
              style={pctBox(frame, box)}
              className="pointer-events-none border border-slate-700/80"
            >
              {frame.h > 48 && frame.w > 70 ? (
                <div className="flex h-[18px] items-center justify-between gap-1 overflow-hidden bg-slate-900/90 px-1.5 font-mono text-[10px] font-semibold tracking-wider text-slate-300 uppercase">
                  <span className="truncate">{frame.sector}</span>
                  <span className={clsx("shrink-0", toneClass(frame.change))}>{pctText(frame.change)}</span>
                </div>
              ) : null}
            </div>
          ))}
          {tiles.map((tile) => (
            <Tile
              key={tile.key}
              tile={tile}
              box={box}
              selected={selected === tile.key}
              onSelect={setSelected}
            />
          ))}
        </div>
      )}

      <footer className="flex min-h-[2.25rem] flex-wrap items-center gap-x-6 gap-y-1 rounded-lg bg-[#05070b] px-3 py-1.5 font-mono text-[11px] ring-1 ring-slate-800">
        {selectedStock ? (
          <>
            <span className="font-bold tracking-wider text-slate-100">{selectedStock.symbol}</span>
            <span className="truncate text-slate-400">{selectedStock.name}</span>
            <span className="text-slate-500">
              SECTOR <span className="text-slate-100">{selectedStock.sector}</span>
            </span>
            <span className="text-slate-500">
              PRICE <span className="text-slate-100">{price(selectedStock.price)}</span>
            </span>
            <span className="text-slate-500">
              CHANGE{" "}
              <span className={toneClass(selectedStock.change_pct)}>
                {formatChangePct(selectedStock.change_pct)}
              </span>
            </span>
            <span className="text-slate-500">
              PREV CLOSE <span className="text-slate-100">{price(selectedStock.previous_close)}</span>
            </span>
            <span className="text-slate-500">
              DAY{" "}
              <span className="text-slate-100">
                {price(selectedStock.day_low)} – {price(selectedStock.day_high)}
              </span>
            </span>
            <span className="text-slate-500">
              52W{" "}
              <span className="text-slate-100">
                {price(selectedStock.year_low)} – {price(selectedStock.year_high)}
              </span>
            </span>
            <span className="text-slate-500">
              VOLUME <span className="text-slate-100">{compactNumber(selectedStock.volume)}</span>
            </span>
            <span className="text-slate-500">
              MKT CAP <span className="text-slate-100">{crore(selectedStock.market_cap)}</span>
            </span>
            <span className="text-slate-500">
              AS OF{" "}
              <span className="text-slate-100">{dateTimeLabel(unixToIso(selectedStock.as_of))}</span>
            </span>
          </>
        ) : (
          <span className="text-slate-500">
            SELECT A TILE OR ROW FOR FULL DETAIL · HATCHED = UNKNOWN · DELAYED QUOTES
          </span>
        )}
      </footer>
    </div>
  );
}
