// Pre-market: the NSE pre-open auction (09:00–09:08 IST) for every F&O stock,
// captured automatically each trading morning, and the day's algorithmic
// watchlist built from it. Read-only; the screens rank situations, they are
// not investment advice, and the page says so.

import { clsx } from "clsx";
import { useMemo, useState } from "react";

import { Glyph } from "@/components/icons";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Select,
  SkeletonRows,
  StatCard,
  Table,
  Td,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { dateTime } from "@/lib/format";
import {
  crore,
  pctText,
  price,
  toneClass,
  type PremarketPick,
  type PremarketScreen,
  type PremarketStock,
  usePremarket,
  useRefreshMarketSnapshot,
} from "@/lib/markets";
import { useAuth } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";

const SCREEN_STYLE: Record<string, { icon: "trendUp" | "trendDown" | "alert" | "rocket"; ring: string; chip: string }> = {
  momentum_up: {
    icon: "trendUp",
    ring: "ring-profit-500/25",
    chip: "bg-profit-500/10 text-profit-700 dark:text-profit-400",
  },
  momentum_down: {
    icon: "trendDown",
    ring: "ring-loss-500/25",
    chip: "bg-loss-500/10 text-loss-700 dark:text-loss-400",
  },
  reversal: {
    icon: "alert",
    ring: "ring-amber-500/25",
    chip: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
  breakout: {
    icon: "rocket",
    ring: "ring-accent-500/25",
    chip: "bg-accent-500/10 text-accent-700 dark:text-accent-300",
  },
};

/** Book imbalance −1..1 as a centred two-sided bar. */
function ImbalanceBar({ value }: { value: number }) {
  const width = Math.min(Math.abs(value), 1) * 50;
  return (
    <span
      className="relative inline-block h-1.5 w-24 rounded-full bg-slate-200 dark:bg-white/10"
      title={`${value > 0 ? "Buyers" : "Sellers"} ${Math.abs(value * 100).toFixed(0)}% net`}
    >
      <span className="absolute inset-y-0 left-1/2 w-px bg-slate-400/60" />
      <span
        className={clsx(
          "absolute inset-y-0 rounded-full",
          value >= 0 ? "left-1/2 bg-profit-500" : "right-1/2 bg-loss-500",
        )}
        style={{ width: `${width}%` }}
      />
    </span>
  );
}

function PickRow({ pick }: { pick: PremarketPick }) {
  return (
    <li className="rounded-xl px-3 py-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-white/[0.03]">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-slate-900 dark:text-white">{pick.symbol}</p>
          <p className="text-[11px] text-slate-500">{pick.sector}</p>
        </div>
        <div className="text-right tabular-nums">
          <p className="text-sm text-slate-800 dark:text-slate-100">{price(pick.iep)}</p>
          <p className={clsx("text-xs font-semibold", toneClass(pick.change_pct))}>
            {pctText(pick.change_pct)}
          </p>
        </div>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <ImbalanceBar value={pick.imbalance} />
        <span className="text-[11px] text-slate-500">score {pick.score.toFixed(1)}</span>
      </div>
      <ul className="mt-1.5 space-y-0.5 text-[11px] text-slate-500 dark:text-slate-400">
        {pick.reasons.map((reason) => (
          <li key={reason} className="flex gap-1.5">
            <span aria-hidden>·</span>
            {reason}
          </li>
        ))}
      </ul>
    </li>
  );
}

function ScreenCard({ screen }: { screen: PremarketScreen }) {
  const style = SCREEN_STYLE[screen.key] ?? SCREEN_STYLE.breakout;
  return (
    <Card
      title={screen.title}
      subtitle={screen.description}
      icon={<Glyph name={style.icon} className="size-3.5" />}
      className={clsx("ring-1", style.ring)}
      bodyClassName="p-2"
      actions={
        <span className={clsx("rounded-full px-2 py-0.5 text-xs font-semibold", style.chip)}>
          {screen.picks.length}
        </span>
      }
    >
      {screen.picks.length === 0 ? (
        <p className="px-3 py-6 text-center text-xs text-slate-500">No stock met this screen today.</p>
      ) : (
        <ul>
          {screen.picks.map((pick) => (
            <PickRow key={pick.symbol} pick={pick} />
          ))}
        </ul>
      )}
    </Card>
  );
}

type SortKey = "change_pct" | "imbalance" | "turnover";

function AllStocks({ stocks }: { stocks: PremarketStock[] }) {
  const [sort, setSort] = useState<SortKey>("change_pct");
  const [sector, setSector] = useState("");
  const sectors = useMemo(() => [...new Set(stocks.map((s) => s.sector))].sort(), [stocks]);
  const rows = useMemo(
    () =>
      stocks
        .filter((stock) => !sector || stock.sector === sector)
        .sort((a, b) =>
          sort === "turnover" ? b.turnover - a.turnover : Math.abs(b[sort]) - Math.abs(a[sort]),
        ),
    [stocks, sort, sector],
  );
  return (
    <Card
      title="All F&O stocks in the pre-open"
      subtitle={`${rows.length} stocks · IEP = indicative equilibrium (opening) price`}
      icon={<Glyph name="list" className="size-3.5" />}
      bodyClassName="px-2 pb-2"
      actions={
        <div className="flex gap-2">
          <div className="w-40">
            <Select
              value={sector}
              onChange={(event) => setSector(event.target.value)}
              aria-label="Filter by sector"
              className="h-8 py-1 text-xs"
            >
              <option value="">All sectors</option>
              {sectors.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-40">
            <Select
              value={sort}
              onChange={(event) => setSort(event.target.value as SortKey)}
              aria-label="Sort by"
              className="h-8 py-1 text-xs"
            >
              <option value="change_pct">Biggest gap</option>
              <option value="imbalance">Strongest imbalance</option>
              <option value="turnover">Highest turnover</option>
            </Select>
          </div>
        </div>
      }
    >
      <div className="max-h-[32rem] overflow-y-auto">
        <Table headers={["Symbol", "Sector", "Prev close", "IEP", "Gap", "Book", "Turnover", "Mkt cap"]} dense>
          {rows.map((stock) => (
            <tr key={stock.symbol}>
              <Td dense className="font-semibold text-slate-800 dark:text-slate-100">
                {stock.symbol}
              </Td>
              <Td dense className="text-xs text-slate-500">
                {stock.sector}
              </Td>
              <Td dense className="tabular-nums">{price(stock.previous_close)}</Td>
              <Td dense className="tabular-nums">{price(stock.iep)}</Td>
              <Td dense className={clsx("font-semibold tabular-nums", toneClass(stock.change_pct))}>
                {pctText(stock.change_pct)}
              </Td>
              <Td dense>
                <ImbalanceBar value={stock.imbalance} />
              </Td>
              <Td dense className="text-xs tabular-nums text-slate-500">
                {crore(stock.turnover)}
              </Td>
              <Td dense className="text-xs tabular-nums text-slate-500">
                {crore(stock.market_cap)}
              </Td>
            </tr>
          ))}
        </Table>
      </div>
    </Card>
  );
}

export function PremarketPage() {
  const [date, setDate] = useState<string | null>(null);
  const premarket = usePremarket(date);
  const isAdmin = useAuth((state) => state.user?.is_platform_admin ?? false);
  const refresh = useRefreshMarketSnapshot();
  const data = premarket.data;

  const fetchNow = () =>
    refresh.mutate("preopen", {
      onSuccess: (result) => toastSuccess("Pre-open snapshot fetched", `Trading day ${result.trade_date}`),
      onError: (error) =>
        toastError("NSE did not answer", error instanceof ApiError ? error.detail : undefined),
    });

  return (
    <div className="am-fade-in">
      <PageHeader
        eyebrow="Markets · NSE pre-open"
        title="Pre-market"
        description="The 09:00–09:08 IST pre-open auction for every F&O stock, captured automatically each trading morning, and the day's watchlist built from it."
        actions={
          <>
            {data?.dates && data.dates.length > 0 ? (
              <div className="w-40">
                <Select
                  value={date ?? ""}
                  onChange={(event) => setDate(event.target.value || null)}
                  aria-label="Trading day"
                  className="h-8 py-1 text-xs"
                >
                  <option value="">Latest</option>
                  {data.dates.map((day) => (
                    <option key={day} value={day}>
                      {day}
                    </option>
                  ))}
                </Select>
              </div>
            ) : null}
            {isAdmin ? (
              <Button size="sm" variant="secondary" onClick={fetchNow} loading={refresh.isPending}>
                <Glyph name="history" className="size-3.5" />
                Fetch now
              </Button>
            ) : null}
          </>
        }
      />

      {premarket.isLoading ? (
        <SkeletonRows rows={6} cols={4} />
      ) : !data || !data.available ? (
        <Card>
          <EmptyState
            icon={<Glyph name="clock" className="size-5" />}
            title="No pre-open snapshot yet"
            body="The platform captures the NSE pre-open auction automatically at about 09:08 IST on every trading day. It will appear here after the next session."
          />
        </Card>
      ) : (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <Badge color={data.stale ? "amber" : "green"} dot>
              {data.stale ? `Showing ${data.trade_date}` : "Today's pre-open"}
            </Badge>
            <span>Auction as of {data.as_of ? dateTime(data.as_of) : "—"}</span>
            <span aria-hidden>·</span>
            <span>Fetched {dateTime(data.fetched_at)}</span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Opening higher"
              value={data.summary.advances}
              icon={<Glyph name="trendUp" />}
              tone="profit"
              sub={`of ${data.summary.stocks} F&O stocks`}
            />
            <StatCard
              label="Opening lower"
              value={data.summary.declines}
              icon={<Glyph name="trendDown" />}
              tone="loss"
              sub={`${data.summary.unchanged} unchanged`}
            />
            <StatCard
              label="Advance / decline"
              value={
                data.summary.declines
                  ? (data.summary.advances / data.summary.declines).toFixed(2)
                  : "—"
              }
              icon={<Glyph name="pulse" />}
              tone="accent"
              sub={data.summary.advances > data.summary.declines ? "Buyers dominate the open" : "Sellers dominate the open"}
            />
            <StatCard
              label="Pre-open turnover"
              value={crore(data.summary.total_traded_value)}
              icon={<Glyph name="receipt" />}
              tone="violet"
              sub="Matched in the auction"
            />
          </div>

          <div className="flex items-start gap-3 rounded-2xl border border-amber-500/25 bg-amber-500/[0.06] p-4 text-xs leading-relaxed text-amber-900 dark:text-amber-100/80">
            <Glyph name="alert" className="mt-0.5 size-4 text-amber-500" />
            <span>
              <strong className="font-semibold">Not investment advice.</strong>{" "}
              {data.disclaimer} Gaps often fill in the first hour; confirm with price action after
              09:15 and size positions to your own risk limits.
            </span>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {data.screens.map((screen) => (
              <ScreenCard key={screen.key} screen={screen} />
            ))}
          </div>

          <AllStocks stocks={data.stocks} />
        </div>
      )}
    </div>
  );
}
