// Building blocks for the live market pages (Market update, Market
// intelligence). Presentational only: every value arrives from
// /markets/pulse, and a missing one renders as "—" / UNKNOWN, never 0.

import { clsx } from "clsx";
import { Link } from "react-router";

import { Glyph } from "@/components/icons";
import { Badge, Card, EmptyState, surface } from "@/components/ui";
import {
  type Breadth,
  type FoStock,
  type InstitutionalFlow,
  type MarketPulse,
  type MarketSession,
  pctText,
  price,
  type QuoteRow,
  rangePosition,
  SESSION_LABEL,
  type SectorMove,
  toneClass,
  type TrendRegime,
} from "@/lib/markets";

export function SessionBadge({ session }: { session: MarketSession }) {
  const color = session.state === "open" ? "green" : session.state === "pre_open" ? "amber" : "slate";
  return (
    <Badge color={color} dot>
      {SESSION_LABEL[session.state]}
    </Badge>
  );
}

function IndexCard({ quote, emphasis }: { quote: QuoteRow; emphasis?: string }) {
  const range =
    quote.day_low !== null && quote.day_high !== null && quote.price !== null && quote.day_high > quote.day_low
      ? (quote.price - quote.day_low) / (quote.day_high - quote.day_low)
      : null;
  return (
    <div className={clsx(surface, "p-4")}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{quote.name}</p>
        {emphasis ? <span className="text-[10px] font-semibold text-slate-400">{emphasis}</span> : null}
      </div>
      <p className="mt-1.5 text-xl font-semibold tracking-tight tabular-nums text-slate-900 dark:text-white">
        {price(quote.price)}
      </p>
      <p className={clsx("mt-0.5 text-xs font-semibold tabular-nums", toneClass(quote.change_pct))}>
        {pctText(quote.change_pct)}
      </p>
      {range !== null ? (
        <div className="mt-3" title={`Day range ${price(quote.day_low)} – ${price(quote.day_high)}`}>
          <div className="relative h-1 rounded-full bg-slate-200 dark:bg-white/10">
            <span
              className="absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent-500"
              style={{ left: `${range * 100}%` }}
            />
          </div>
          <div className="mt-1 flex justify-between text-[10px] tabular-nums text-slate-400">
            <span>{price(quote.day_low)}</span>
            <span>{price(quote.day_high)}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function IndexStrip({ pulse }: { pulse: MarketPulse }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
      {pulse.indices.map((quote) => (
        <IndexCard key={quote.symbol} quote={quote} />
      ))}
      <IndexCard quote={pulse.vix} emphasis={pulse.regime.volatility.label.toUpperCase()} />
    </div>
  );
}

export function BreadthCard({ breadth }: { breadth: Breadth }) {
  const total = breadth.advances + breadth.declines + breadth.unchanged || 1;
  return (
    <Card
      title="Market breadth"
      subtitle="Across all NSE F&O stocks"
      icon={<Glyph name="pulse" className="size-3.5" />}
    >
      <div className="flex h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
        <div className="bg-profit-500" style={{ width: `${(breadth.advances / total) * 100}%` }} />
        <div className="bg-slate-400/60" style={{ width: `${(breadth.unchanged / total) * 100}%` }} />
        <div className="bg-loss-500" style={{ width: `${(breadth.declines / total) * 100}%` }} />
      </div>
      <div className="mt-3 grid grid-cols-3 text-center">
        <div>
          <p className="text-lg font-semibold text-profit-600 tabular-nums dark:text-profit-400">{breadth.advances}</p>
          <p className="text-[11px] text-slate-500">Advancing</p>
        </div>
        <div>
          <p className="text-lg font-semibold text-slate-600 tabular-nums dark:text-slate-300">{breadth.unchanged}</p>
          <p className="text-[11px] text-slate-500">Flat</p>
        </div>
        <div>
          <p className="text-lg font-semibold text-loss-600 tabular-nums dark:text-loss-400">{breadth.declines}</p>
          <p className="text-[11px] text-slate-500">Declining</p>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-3 text-xs dark:border-white/[0.06]">
        <div className="flex justify-between">
          <dt className="text-slate-500">A/D ratio</dt>
          <dd className="font-semibold tabular-nums">{breadth.ratio ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">% advancing</dt>
          <dd className="font-semibold tabular-nums">{breadth.pct_advancing ?? "—"}%</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Near 52W high</dt>
          <dd className="font-semibold tabular-nums text-profit-600 dark:text-profit-400">{breadth.near_year_high}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Near 52W low</dt>
          <dd className="font-semibold tabular-nums text-loss-600 dark:text-loss-400">{breadth.near_year_low}</dd>
        </div>
      </dl>
    </Card>
  );
}

const TREND_COLOR: Record<TrendRegime["label"], "green" | "red" | "amber" | "slate"> = {
  Uptrend: "green",
  Downtrend: "red",
  "Range-bound": "amber",
  Unknown: "slate",
};

export function RegimeCard({ title, regime }: { title: string; regime: TrendRegime }) {
  const levels: Array<[string, number | null]> = [
    ["20-day avg", regime.sma20],
    ["50-day avg", regime.sma50],
    ["200-day avg", regime.sma200],
  ];
  return (
    <Card
      title={title}
      subtitle="Trend from daily closes"
      icon={<Glyph name="chart" className="size-3.5" />}
      actions={
        <Badge color={TREND_COLOR[regime.label]} dot>
          {regime.label}
        </Badge>
      }
    >
      <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">{regime.explanation}</p>
      <dl className="mt-3 space-y-1.5 text-xs">
        {levels.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between">
            <dt className="text-slate-500">{label}</dt>
            <dd className="flex items-center gap-2 tabular-nums">
              <span className="font-medium text-slate-800 dark:text-slate-100">{price(value)}</span>
              {value !== null && regime.price !== null ? (
                <span className={clsx("w-14 text-right", toneClass(regime.price - value))}>
                  {pctText(((regime.price - value) / value) * 100, 1)}
                </span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-center text-xs dark:border-white/[0.06]">
        <div>
          <p className="font-semibold tabular-nums">{regime.rsi14 ?? "—"}</p>
          <p className="text-[10px] text-slate-500">RSI (14)</p>
        </div>
        <div>
          <p className={clsx("font-semibold tabular-nums", toneClass(regime.return_5d))}>{pctText(regime.return_5d)}</p>
          <p className="text-[10px] text-slate-500">5 days</p>
        </div>
        <div>
          <p className={clsx("font-semibold tabular-nums", toneClass(regime.return_20d))}>{pctText(regime.return_20d)}</p>
          <p className="text-[10px] text-slate-500">20 days</p>
        </div>
      </div>
    </Card>
  );
}

function FlowBar({ value, max }: { value: number | null; max: number }) {
  if (value === null) return <span className="text-xs text-slate-400">—</span>;
  const width = max ? Math.min(Math.abs(value) / max, 1) * 50 : 0;
  return (
    <span className="relative block h-2 w-full rounded-full bg-slate-100 dark:bg-white/[0.06]">
      <span className="absolute inset-y-0 left-1/2 w-px bg-slate-400/50" />
      <span
        className={clsx("absolute inset-y-0 rounded-full", value >= 0 ? "left-1/2 bg-profit-500" : "right-1/2 bg-loss-500")}
        style={{ width: `${width}%` }}
      />
    </span>
  );
}

export function FlowsCard({ flows }: { flows: InstitutionalFlow[] }) {
  const latest = flows[0];
  const max = Math.max(1, ...flows.flatMap((flow) => [Math.abs(flow.fii_net ?? 0), Math.abs(flow.dii_net ?? 0)]));
  return (
    <Card
      title="Institutional flows"
      subtitle="NSE provisional cash-market data, ₹ crore"
      icon={<Glyph name="layers" className="size-3.5" />}
    >
      {!latest ? (
        <EmptyState
          title="No flow data yet"
          body="FII/DII figures are captured from NSE each evening after the close."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                ["FII / FPI", latest.fii_net],
                ["DII", latest.dii_net],
              ] as Array<[string, number | null]>
            ).map(([label, value]) => (
              <div key={label} className="rounded-xl bg-slate-50 p-3 dark:bg-white/[0.03]">
                <p className="text-[11px] text-slate-500">{label} net</p>
                <p className={clsx("mt-0.5 text-lg font-semibold tabular-nums", toneClass(value))}>
                  {value === null ? "—" : `${value > 0 ? "+" : ""}${Math.round(value).toLocaleString("en-IN")}`}
                </p>
                <p className="text-[10px] text-slate-400">{latest.trade_date}</p>
              </div>
            ))}
          </div>
          {flows.length > 1 ? (
            <table className="mt-4 w-full text-xs">
              <thead className="text-[10px] tracking-wider text-slate-400 uppercase">
                <tr>
                  <th className="pb-1 text-left font-medium">Day</th>
                  <th className="pb-1 text-left font-medium">FII</th>
                  <th className="pb-1 text-left font-medium">DII</th>
                </tr>
              </thead>
              <tbody>
                {flows.slice(0, 10).map((flow) => (
                  <tr key={flow.trade_date}>
                    <td className="py-1 pr-2 text-slate-500 tabular-nums">{flow.trade_date.slice(5)}</td>
                    <td className="w-1/2 py-1 pr-2">
                      <FlowBar value={flow.fii_net} max={max} />
                    </td>
                    <td className="w-1/2 py-1">
                      <FlowBar value={flow.dii_net} max={max} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="mt-3 text-[11px] text-slate-400">A daily history builds up from here, one session at a time.</p>
          )}
        </>
      )}
    </Card>
  );
}

export function SectorBars({ sectors }: { sectors: SectorMove[] }) {
  const max = Math.max(0.5, ...sectors.map((sector) => Math.abs(sector.change_pct)));
  return (
    <Card
      title="Sector performance"
      subtitle="Market-cap weighted, F&O constituents"
      icon={<Glyph name="chart" className="size-3.5" />}
      actions={
        <Link
          to="/app/heatmap"
          className="inline-flex items-center gap-1 text-xs font-medium text-accent-600 hover:text-accent-500 dark:text-accent-400"
        >
          Heatmap <Glyph name="arrowRight" className="size-3" />
        </Link>
      }
    >
      <ul className="space-y-2">
        {sectors.map((sector) => (
          <li key={sector.sector} className="grid grid-cols-[8.5rem_1fr_3.5rem] items-center gap-3 text-xs">
            <span className="truncate text-slate-700 dark:text-slate-200" title={`${sector.members} stocks · ${sector.advancing} advancing · leader ${sector.leader} · laggard ${sector.laggard}`}>
              {sector.sector}
            </span>
            <span className="relative h-2 rounded-full bg-slate-100 dark:bg-white/[0.05]">
              <span className="absolute inset-y-0 left-1/2 w-px bg-slate-400/50" />
              <span
                className={clsx(
                  "absolute inset-y-0 rounded-full",
                  sector.change_pct >= 0 ? "left-1/2 bg-profit-500" : "right-1/2 bg-loss-500",
                )}
                style={{ width: `${(Math.abs(sector.change_pct) / max) * 50}%` }}
              />
            </span>
            <span className={clsx("text-right font-semibold tabular-nums", toneClass(sector.change_pct))}>
              {pctText(sector.change_pct)}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function MoversCard({
  title,
  stocks,
  icon,
  showRange,
}: {
  title: string;
  stocks: FoStock[];
  icon: "trendUp" | "trendDown" | "rocket";
  showRange?: boolean;
}) {
  return (
    <Card title={title} icon={<Glyph name={icon} className="size-3.5" />} bodyClassName="p-2">
      {stocks.length === 0 ? (
        <EmptyState title="Nothing to show" />
      ) : (
        <ul>
          {stocks.map((stock) => {
            const position = rangePosition(stock);
            return (
              <li key={stock.symbol} className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block font-medium text-slate-800 dark:text-slate-100">{stock.symbol}</span>
                  <span className="block truncate text-[11px] text-slate-500">{stock.sector}</span>
                </span>
                <span className="text-right tabular-nums">
                  <span className="block text-slate-700 dark:text-slate-200">{price(stock.price)}</span>
                  {showRange && position !== null ? (
                    <span className="block text-[11px] text-slate-500">{Math.round(position * 100)}% of 52W range</span>
                  ) : (
                    <span className={clsx("block text-xs font-semibold", toneClass(stock.change_pct))}>
                      {pctText(stock.change_pct)}
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

const REGION_ORDER = ["US", "Europe", "Asia", "Commodities", "Currency"];

export function GlobalCues({ cues }: { cues: MarketPulse["global"] }) {
  return (
    <Card title="Global cues" subtitle="Latest session per market, delayed" icon={<Glyph name="radar" className="size-3.5" />}>
      {/* Container query: two columns only when the card itself is wide enough. */}
      <div className="@container">
        <div className="grid gap-x-6 gap-y-4 @md:grid-cols-2">
        {REGION_ORDER.map((region) => {
          const members = cues.filter((cue) => cue.region === region);
          if (members.length === 0) return null;
          return (
            <div key={region}>
              <p className="mb-1.5 text-[10px] font-semibold tracking-[0.14em] text-slate-400 uppercase">{region}</p>
              <ul className="space-y-1.5">
                {members.map((cue) => (
                  <li key={cue.symbol} className="flex items-center justify-between text-xs">
                    <span className="truncate text-slate-700 dark:text-slate-200">{cue.name}</span>
                    <span className="flex gap-3 tabular-nums">
                      <span className="text-slate-500">{price(cue.price)}</span>
                      <span className={clsx("w-14 text-right font-semibold", toneClass(cue.change_pct))}>
                        {pctText(cue.change_pct)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
        </div>
      </div>
    </Card>
  );
}
