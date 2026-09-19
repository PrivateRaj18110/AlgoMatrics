// AI-CIO · Today's movers: the ranked forecast of major moves, with reasons,
// the filings behind each pick, intraday catalysts and — after the close — the grade.

import { clsx } from "clsx";
import { useMemo, useState } from "react";

import { Glyph } from "@/components/icons";
import { Badge, Button, Card, EmptyState, Input, Select, SkeletonRows, Table, Td } from "@/components/ui";
import {
  chance,
  ratio,
  signedPct,
  STAGE_LABEL,
  type DayOutcome,
  type ForecastStock,
  useMovers,
  useRunMoversJob,
} from "@/lib/movers";

import { CatalystChip, ChanceBar, DirectionChip, ImpactMeter, istDay, istStamp, ProbabilityRing } from "./parts";

const TOP = 10;

function Outcome({ stock, outcome }: { stock: ForecastStock; outcome: DayOutcome | null }) {
  const result = outcome?.stocks[stock.symbol];
  if (!result) return null;
  const [change, major] = result;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 font-data text-[11px] font-semibold",
        major ? "bg-profit-500/10 text-profit-700 dark:text-profit-400" : "bg-slate-500/10 text-slate-600 dark:text-slate-300",
      )}
      title={major ? `Moved at least ${stock.threshold_pct}%: counted as a hit` : `Stayed inside ±${stock.threshold_pct}%`}
    >
      Closed {signedPct(change)}
      <span>{major ? "· HIT" : "· no major move"}</span>
    </span>
  );
}

function PickCard({ stock, outcome }: { stock: ForecastStock; outcome: DayOutcome | null }) {
  return (
    <article
      aria-label={`${stock.symbol} forecast`}
      className="flex min-w-0 flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/[0.07] dark:bg-white/[0.02] dark:shadow-none"
    >
      <header className="flex items-center gap-3">
        <ProbabilityRing probability={stock.probability} />
        <div className="min-w-0 flex-1">
          <p className="flex items-baseline gap-2">
            <span className="font-data text-[11px] text-slate-400">#{stock.rank}</span>
            <span className="truncate text-base font-semibold tracking-tight text-slate-900 dark:text-white">{stock.symbol}</span>
          </p>
          <p className="truncate text-xs text-slate-500">{stock.sector}</p>
        </div>
      </header>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <DirectionChip direction={stock.direction} confidence={stock.direction_confidence} />
        <span className="text-[11px] text-slate-500">
          chance of <span className="font-semibold text-slate-700 dark:text-slate-200">±{stock.threshold_pct}%</span> or more
        </span>
      </div>

      <dl className="grid grid-cols-3 gap-2 rounded-xl bg-slate-50 px-3 py-2 text-center dark:bg-white/[0.03]">
        <div>
          <dt className="text-[10px] tracking-wide text-slate-500 uppercase">Pre-open</dt>
          <dd className={clsx("font-data text-sm font-semibold tabular-nums", (stock.gap_pct ?? 0) > 0 ? "text-profit-600 dark:text-profit-400" : (stock.gap_pct ?? 0) < 0 ? "text-loss-600 dark:text-loss-400" : "text-slate-700 dark:text-slate-200")}>
            {stock.gap_pct === null ? "—" : signedPct(stock.gap_pct)}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] tracking-wide text-slate-500 uppercase">Usual day</dt>
          <dd className="font-data text-sm font-semibold tabular-nums text-slate-700 dark:text-slate-200">±{stock.typical_move_pct.toFixed(1)}%</dd>
        </div>
        <div>
          <dt className="text-[10px] tracking-wide text-slate-500 uppercase">Last session</dt>
          <dd className="font-data text-sm font-semibold tabular-nums text-slate-700 dark:text-slate-200">{signedPct(stock.prev_change_pct)}</dd>
        </div>
      </dl>

      {stock.reasons.length ? (
        <ul className="space-y-1">
          {stock.reasons.slice(0, 3).map((reason) => (
            <li key={reason.feature} className="flex gap-2 text-xs text-slate-600 dark:text-slate-300">
              <span aria-hidden className="mt-1.5 size-1 shrink-0 rounded-full bg-accent-500" />
              {reason.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-slate-500">No single driver stands out; it ranks on volatility alone.</p>
      )}

      {stock.catalysts.length || stock.flags.ban || stock.flags.ex_adjustment ? (
        <div className="flex flex-wrap gap-1.5">
          {stock.catalysts.map((catalyst) => (
            <CatalystChip key={catalyst.id} catalyst={catalyst} />
          ))}
        </div>
      ) : null}

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2 text-[11px] text-slate-500 dark:border-white/[0.06]">
        <span>{stock.direction === "either" ? "No directional evidence" : `Direction from ${stock.direction_basis}`}</span>
        <Outcome stock={stock} outcome={outcome} />
      </footer>
    </article>
  );
}

/** How the day's hit rate compares with picking stocks at random, in words. */
function liftPhrase(lift: number | null): string | null {
  if (lift === null || !Number.isFinite(lift)) return null;
  if (lift >= 1.05) return `${lift.toFixed(1)}× better than picking at random`;
  if (lift <= 0.95) return "worse than picking at random today";
  return "about the same as picking at random";
}

function GradeBanner({ outcome, stage }: { outcome: DayOutcome; stage: "overnight" | "opening" }) {
  const grade = outcome.grades[stage] ?? outcome.grades.opening ?? outcome.grades.overnight;
  if (!grade) return null;
  const good = (grade.lift ?? 0) >= 1.5;
  const phrase = liftPhrase(grade.lift);
  // On a broad sell-off or rally most stocks clear their bar, and stock-specific
  // signals carry little extra information; say so rather than leave it unexplained.
  const broad = (grade.base_rate ?? 0) >= 0.15 && (grade.lift ?? 0) < 1.2;
  return (
    <div
      className={clsx(
        "flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border px-4 py-3",
        good ? "border-profit-500/25 bg-profit-500/[0.06]" : "border-slate-200 bg-slate-50 dark:border-white/[0.07] dark:bg-white/[0.02]",
      )}
      role="status"
    >
      <span className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
        <Glyph name="shield" className="size-4 text-accent-500" />
        Graded on the close
      </span>
      <span className="text-sm text-slate-600 dark:text-slate-300">
        <b className="font-data">{grade.hits}</b> of the top {grade.top_k} made a major move ({ratio(grade.precision)}), against{" "}
        <b className="font-data">{ratio(grade.base_rate, 1)}</b> of all {grade.universe} stocks
        {phrase ? <> — {phrase}</> : null}.
      </span>
      {grade.direction_calls ? (
        <span className="text-sm text-slate-600 dark:text-slate-300">
          Direction right on {grade.direction_right} of {grade.direction_calls}.
        </span>
      ) : null}
      {broad ? (
        <span className="text-xs text-slate-500">
          A market-wide move day: {Math.round((grade.base_rate ?? 0) * 100)}% of all F&O stocks made a major move, so
          stock-specific signals added little.
        </span>
      ) : null}
      {grade.missed_symbols.length ? (
        <span className="text-xs text-slate-500">Biggest misses: {grade.missed_symbols.slice(0, 6).join(", ")}</span>
      ) : null}
    </div>
  );
}

export function MoversTab({ isAdmin }: { isAdmin: boolean }) {
  const [date, setDate] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [onlyCatalysts, setOnlyCatalysts] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const movers = useMovers(date);
  const run = useRunMoversJob();
  const data = movers.data;

  const rows = useMemo(() => {
    if (!data?.available) return [];
    const needle = query.trim().toUpperCase();
    return data.forecast.stocks.filter(
      (stock) =>
        (!needle || stock.symbol.includes(needle) || stock.sector.toUpperCase().includes(needle)) &&
        (!onlyCatalysts || stock.catalysts.some((c) => c.impact >= 0.3) || stock.flags.results),
    );
  }, [data, query, onlyCatalysts]);

  if (movers.isLoading) return <SkeletonRows rows={6} cols={4} />;
  if (movers.isError || !data) {
    return (
      <Card>
        <EmptyState title="AI-CIO did not answer" body="The forecast service is unreachable right now; this page retries every two minutes." />
      </Card>
    );
  }
  if (!data.available) {
    return (
      <Card>
        <EmptyState
          title="No forecast yet"
          body="AI-CIO builds an overnight forecast from 08:00 IST each trading day and the full opening forecast right after the 09:08 pre-open auction. The first one appears on the next trading morning."
          action={
            isAdmin ? (
              <Button size="sm" onClick={() => run.mutate("forecast")} loading={run.isPending}>
                Build a forecast now
              </Button>
            ) : undefined
          }
        />
      </Card>
    );
  }

  const { forecast, outcome } = data;
  const top = forecast.stocks.slice(0, TOP);
  const visible = showAll || query || onlyCatalysts ? rows : rows.slice(0, 50);
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge color={forecast.stage === "opening" ? "green" : "blue"} dot>
            {STAGE_LABEL[forecast.stage]}
          </Badge>
          <span className="text-sm font-medium text-slate-800 dark:text-slate-100">{istDay(data.trade_date)}</span>
          <span className="text-xs text-slate-500">
            built {istStamp(forecast.generated_at, today)} IST ·{" "}
            {forecast.stage === "opening" ? "includes the 09:08 pre-open auction" : "before the auction; refreshed after 09:08"}
          </span>
          {data.stale ? <Badge color="amber">Not today</Badge> : null}
        </div>
        <div className="flex items-center gap-2">
          {data.dates.length > 1 ? (
            <div className="w-44">
              <Select aria-label="Forecast date" value={date ?? ""} onChange={(event) => setDate(event.target.value || null)}>
                <option value="">Latest</option>
                {data.dates.map((day) => (
                  <option key={day} value={day}>
                    {istDay(day)}
                  </option>
                ))}
              </Select>
            </div>
          ) : null}
          {isAdmin ? (
            <Button size="sm" variant="secondary" onClick={() => run.mutate("forecast")} loading={run.isPending}>
              Rebuild
            </Button>
          ) : null}
        </div>
      </div>

      {outcome ? <GradeBanner outcome={outcome} stage={forecast.stage} /> : null}

      <section className="grid gap-4 rounded-2xl border border-slate-200 bg-gradient-to-br from-accent-500/[0.06] via-transparent to-transparent p-4 sm:grid-cols-4 dark:border-white/[0.07]">
        <div>
          <p className="text-[11px] font-medium tracking-wide text-slate-500 uppercase">Expected major movers</p>
          <p className="mt-0.5 font-data text-2xl font-semibold tabular-nums text-slate-900 dark:text-white">
            ~{Math.round(forecast.expected_majors)}
            <span className="ml-1 text-sm font-normal text-slate-500">of {forecast.universe}</span>
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium tracking-wide text-slate-500 uppercase">Major move means</p>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{forecast.threshold_rule}</p>
        </div>
        <div>
          <p className="text-[11px] font-medium tracking-wide text-slate-500 uppercase">Model</p>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
            {forecast.model.source === "fitted"
              ? `Fitted on ${forecast.model.days ?? "?"} graded sessions`
              : "Starting weights (not yet fitted)"}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium tracking-wide text-slate-500 uppercase">Top pick</p>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
            <b>{top[0]?.symbol ?? "—"}</b> · {chance(top[0]?.probability)} chance
          </p>
        </div>
      </section>

      <div>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
          <Glyph name="rocket" className="size-4 text-accent-500" />
          Most likely to make a major move
        </h2>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,15rem),1fr))] gap-4">
          {top.map((stock) => (
            <PickCard key={stock.symbol} stock={stock} outcome={outcome} />
          ))}
        </div>
      </div>

      {data.intraday.length ? (
        <Card
          title="New filings since the open"
          subtitle="Material exchange filings on F&O stocks after 09:08 — not in this morning's forecast"
          icon={<Glyph name="alert" className="size-3.5" />}
        >
          <ul className="divide-y divide-slate-100 dark:divide-white/[0.05]">
            {data.intraday.slice(0, 10).map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <span className="w-12 font-data text-xs text-slate-500">{istStamp(item.at, data.trade_date)}</span>
                <span className="w-24 font-semibold text-slate-900 dark:text-white">{item.symbol}</span>
                <CatalystChip catalyst={item} />
                <ImpactMeter impact={item.impact} />
                <span className="min-w-0 flex-1 truncate text-xs text-slate-500">{item.title}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card
        title="Every F&O stock, ranked"
        subtitle={`${forecast.stocks.length} stocks · chance of a major move today`}
        icon={<Glyph name="list" className="size-3.5" />}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-44">
              <Input aria-label="Filter stocks" placeholder="Symbol or sector" value={query} onChange={(event) => setQuery(event.target.value)} />
            </div>
            <label className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300">
              <input type="checkbox" checked={onlyCatalysts} onChange={(event) => setOnlyCatalysts(event.target.checked)} />
              With news only
            </label>
          </div>
        }
      >
        <Table headers={["#", "Stock", "Chance", "Direction", "Pre-open", "Needs", "Why", outcome ? "Result" : ""]}>
          {visible.map((stock) => (
            <tr key={stock.symbol}>
              <Td className="font-data text-xs text-slate-400">{stock.rank}</Td>
              <Td>
                <span className="font-semibold text-slate-900 dark:text-white">{stock.symbol}</span>
                <span className="block text-[11px] text-slate-500">{stock.sector}</span>
              </Td>
              <Td>
                <ChanceBar probability={stock.probability} />
              </Td>
              <Td>
                <DirectionChip direction={stock.direction} />
              </Td>
              <Td className="font-data tabular-nums">{stock.gap_pct === null ? "—" : signedPct(stock.gap_pct)}</Td>
              <Td className="font-data tabular-nums text-slate-500">±{stock.threshold_pct}%</Td>
              <Td>
                <span className="block max-w-xs truncate text-xs text-slate-500" title={stock.reasons[0]?.text}>
                  {stock.reasons[0]?.text ?? "—"}
                </span>
              </Td>
              <Td>{outcome ? <Outcome stock={stock} outcome={outcome} /> : null}</Td>
            </tr>
          ))}
        </Table>
        {!showAll && !query && !onlyCatalysts && rows.length > 50 ? (
          <div className="mt-3 text-center">
            <Button size="sm" variant="ghost" onClick={() => setShowAll(true)}>
              Show all {rows.length}
            </Button>
          </div>
        ) : null}
      </Card>

      <p className="text-xs text-slate-500">{data.disclaimer}</p>
    </div>
  );
}
