import { clsx } from "clsx";
import { useState } from "react";

import {
  Badge,
  Card,
  EmptyState,
  PageHeader,
  Select,
  SkeletonRows,
  StatCard,
  Table,
  Td,
} from "@/components/ui";
import {
  useInstitutionalFlow,
  useMarketIntelIndices,
  useMarketIntelNews,
  useMarketIntelStatus,
  useOptionsSnapshot,
  useRankings,
  useRegime,
} from "@/lib/hooks";
import { dateOnly } from "@/lib/format";
import type { RankingRow } from "@/types/api";

/**
 * Market Intelligence (AI-CIO): a read-only, advisory overlay. It shows the
 * current market regime, the day's ranked opportunities with their dimension
 * breakdown, notable options / institutional-flow reads, and recent news. It
 * never places a trade — it only informs.
 */

const DIMENSION_LABELS: Record<string, string> = {
  rs_60d: "Rel. strength (60d)",
  mom_20d: "Momentum (20d)",
  turnover_20d_avg: "Turnover (20d avg)",
  atr_pct: "ATR %",
  hv_ratio_10_60: "HV ratio 10/60",
  oi_score: "Options OI",
  if_score: "Institutional flow",
};

function regimeColor(label: string): "green" | "red" | "amber" | "blue" | "slate" {
  if (label.startsWith("trending")) return "blue";
  if (label === "risk_on") return "green";
  if (label === "risk_off") return "red";
  if (label === "recovery_transition") return "amber";
  return "slate";
}

function sentimentColor(label: string | null): "green" | "red" | "slate" {
  if (label === "positive") return "green";
  if (label === "negative") return "red";
  return "slate";
}

function fmtDim(value: number | null): string {
  if (value === null) return "—";
  if (Math.abs(value) >= 1000) {
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(
      value,
    );
  }
  return value.toFixed(2);
}

function pctOf(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/** Per-dimension min/max across the visible rankings, for bar normalisation. */
function dimensionExtents(rows: RankingRow[]): Record<string, { min: number; max: number }> {
  const extents: Record<string, { min: number; max: number }> = {};
  for (const row of rows) {
    for (const dim of row.dimensions) {
      if (dim.value === null) continue;
      const current = extents[dim.name];
      extents[dim.name] = current
        ? { min: Math.min(current.min, dim.value), max: Math.max(current.max, dim.value) }
        : { min: dim.value, max: dim.value };
    }
  }
  return extents;
}

function barWidth(value: number | null, extent?: { min: number; max: number }): number {
  if (value === null || !extent || extent.max === extent.min) return value === null ? 0 : 50;
  return ((value - extent.min) / (extent.max - extent.min)) * 100;
}

function RegimePanel() {
  const { data: regime, isLoading } = useRegime();
  if (isLoading && !regime) {
    return (
      <div className="mb-6">
        <SkeletonRows rows={1} cols={4} />
      </div>
    );
  }
  if (!regime) return null;
  return (
    <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Market regime"
        value={<Badge color={regimeColor(regime.label)}>{regime.label}</Badge>}
        sub={regime.as_of ? `as of ${dateOnly(regime.as_of)}` : undefined}
      />
      <StatCard
        label="HMM confidence"
        value={pctOf(regime.hmm_confidence)}
        sub={regime.hmm_vol_state ? `vol state: ${regime.hmm_vol_state}` : undefined}
      />
      <StatCard
        label="Trend / correlation"
        value={regime.adx_14 !== null ? `ADX ${regime.adx_14.toFixed(0)}` : "—"}
        sub={
          regime.avg_pairwise_corr !== null
            ? `avg corr ${regime.avg_pairwise_corr.toFixed(2)}`
            : undefined
        }
      />
      <StatCard label="Breadth > 20d MA" value={pctOf(regime.breadth_pct_above_ma20)} />
    </div>
  );
}

function TickerDetail({ ticker, row, rows }: { ticker: string; row?: RankingRow; rows: RankingRow[] }) {
  const { data: options } = useOptionsSnapshot(ticker);
  const { data: flow } = useInstitutionalFlow(ticker);
  const extents = dimensionExtents(rows);
  return (
    <Card title={`${ticker} — dimension breakdown`}>
      {row ? (
        <div className="space-y-2">
          {row.dimensions.map((dim) => (
            <div key={dim.name} className="flex items-center gap-3">
              <span className="w-36 shrink-0 text-xs text-slate-500 dark:text-slate-400">
                {DIMENSION_LABELS[dim.name] ?? dim.name}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-surface-800">
                <div
                  className="h-full rounded-full bg-accent-500"
                  style={{ width: `${barWidth(dim.value, extents[dim.name])}%` }}
                />
              </div>
              <span className="w-16 shrink-0 text-right text-xs tabular-nums">
                {fmtDim(dim.value)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-500">Select a ticker to see its breakdown.</p>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-3 text-sm dark:border-surface-800">
        <div>
          <p className="text-xs text-slate-400">Options (PCR OI / max pain)</p>
          <p className="tabular-nums">
            {options ? `${options.pcr_oi?.toFixed(2) ?? "—"} / ${fmtDim(options.max_pain)}` : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Institutional flow</p>
          <p className="tabular-nums">
            {flow ? `${flow.if_score.toFixed(2)} (${flow.n_deals ?? 0} deals)` : "no deal"}
          </p>
        </div>
      </div>
    </Card>
  );
}

function RankingsPanel() {
  const { data: indices } = useMarketIntelIndices();
  const [index, setIndex] = useState<string>("");
  const [picked, setPicked] = useState<string | null>(null);
  const { data: rankings, isLoading } = useRankings(20, index || undefined);
  const rows = rankings ?? [];
  const selected = picked ?? rows[0]?.ticker ?? null;
  const selectedRow = rows.find((row) => row.ticker === selected);

  const indexSelect = (
    <Select
      value={index}
      onChange={(event) => {
        setIndex(event.target.value);
        setPicked(null);
      }}
      aria-label="Filter by index"
      className="w-40"
    >
      <option value="">All F&amp;O</option>
      {(indices ?? []).map((group) => (
        <option key={group.value} value={group.value}>
          {group.label}
        </option>
      ))}
    </Select>
  );

  if (isLoading && !rankings) {
    return (
      <Card title="Top opportunities" actions={indexSelect}>
        <SkeletonRows rows={8} cols={4} />
      </Card>
    );
  }
  if (rows.length === 0) {
    return (
      <Card title="Top opportunities" actions={indexSelect}>
        <EmptyState
          title={index ? "No ranked names in this index yet" : "No ranking data yet"}
          body="The AI-CIO pipeline ranks its F&O universe on its own schedule; not every index is fully covered."
        />
      </Card>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="lg:col-span-3">
        <Card title="Top opportunities" actions={indexSelect} className="overflow-hidden">
          <Table headers={["#", "Ticker", "Name", "Score"]} dense>
            {rows.map((row) => (
              <tr
                key={row.ticker}
                onClick={() => setPicked(row.ticker)}
                className={clsx(
                  "cursor-pointer transition-colors",
                  row.ticker === selected
                    ? "bg-accent-500/10"
                    : "hover:bg-slate-50 dark:hover:bg-surface-800/50",
                )}
              >
                <Td dense className="tabular-nums text-slate-400">
                  {row.rank}
                </Td>
                <Td dense className="font-medium">
                  {row.ticker}
                </Td>
                <Td dense className="text-slate-500 dark:text-slate-400">
                  {row.name ?? "—"}
                </Td>
                <Td dense className="tabular-nums">
                  {row.composite_score.toFixed(3)}
                </Td>
              </tr>
            ))}
          </Table>
        </Card>
      </div>
      <div className="lg:col-span-2">
        {selected && <TickerDetail ticker={selected} row={selectedRow} rows={rows} />}
      </div>
    </div>
  );
}

function NewsPanel() {
  const { data: news, isLoading } = useMarketIntelNews();
  const items = news ?? [];
  return (
    <Card title="Recent news" className="mt-4">
      {isLoading && !news ? (
        <SkeletonRows rows={4} cols={2} />
      ) : items.length === 0 ? (
        <EmptyState title="No news yet" body="Headlines appear once the AI-CIO news run has data." />
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-surface-800/60">
          {items.slice(0, 12).map((item, index) => (
            <li key={`${item.ticker}-${index}`} className="flex items-start gap-3 py-2">
              <Badge color="slate" className="mt-0.5 shrink-0">
                {item.ticker}
              </Badge>
              <div className="min-w-0 flex-1">
                <a
                  href={item.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-slate-800 hover:underline dark:text-slate-200"
                >
                  {item.title}
                </a>
                <p className="text-xs text-slate-400">{item.source}</p>
              </div>
              {item.sentiment_label && (
                <Badge color={sentimentColor(item.sentiment_label)} className="mt-0.5 shrink-0">
                  {item.sentiment_label}
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function MarketIntelPage() {
  const { data: status } = useMarketIntelStatus();

  return (
    <div>
      <PageHeader
        title="Market Intelligence"
        description="AI-CIO advisory reads — regime, ranked opportunities, and news. Research and screening only, not a trade signal."
        actions={<Badge color="violet">Advisory · read-only</Badge>}
      />

      {status && !status.configured ? (
        <Card>
          <EmptyState
            title="AI-CIO is not configured"
            body="Set AICIO_DUCKDB_PATH to the AI-CIO DuckDB file to enable regime, rankings, and news."
          />
        </Card>
      ) : (
        <>
          <RegimePanel />
          <RankingsPanel />
          <NewsPanel />
        </>
      )}
    </div>
  );
}
