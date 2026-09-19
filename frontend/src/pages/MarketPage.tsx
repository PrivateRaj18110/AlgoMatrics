import { Link } from "react-router";

import { Glyph } from "@/components/icons";
import {
  BreadthCard,
  FlowsCard,
  GlobalCues,
  IndexStrip,
  MoversCard,
  SectorBars,
  SessionBadge,
} from "@/components/market/MarketWidgets";
import { Card, EmptyState, PageHeader, Skeleton, buttonClass } from "@/components/ui";
import { clockLabel } from "@/lib/wallboard";
import { useMarketPulse } from "@/lib/markets";

/**
 * Market update: the Indian market right now — indices, India VIX, global
 * cues, breadth and sectors across the whole NSE F&O universe, the day's
 * movers and institutional flows. All live data (NSE + Yahoo, delayed); the
 * page shows when it last refreshed and never fills gaps with made-up values.
 */
export function MarketPage() {
  const pulse = useMarketPulse();
  const data = pulse.data;

  return (
    <div className="am-fade-in">
      <PageHeader
        eyebrow="Markets · Live"
        title="Market update"
        description="Indices, global cues, breadth, sectors, movers and institutional flows across the NSE F&O universe. Refreshes every minute."
        actions={
          <>
            {data ? <SessionBadge session={data.session} /> : null}
            {pulse.dataUpdatedAt ? (
              <span className="text-xs text-slate-500">
                Updated {clockLabel(new Date(pulse.dataUpdatedAt).toISOString())}
              </span>
            ) : null}
            <Link to="/app/pre-market" className={buttonClass({ variant: "secondary", size: "sm" })}>
              <Glyph name="clock" className="size-3.5" />
              Pre-market
            </Link>
          </>
        }
      />

      {pulse.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          {Array.from({ length: 7 }).map((_, index) => (
            <Skeleton key={index} className="h-32 rounded-2xl" />
          ))}
        </div>
      ) : !data ? (
        <Card>
          <EmptyState
            icon={<Glyph name="alert" className="size-5" />}
            title="Market data is unavailable right now"
            body="The quote sources did not answer. This page shows nothing rather than stale or invented numbers; it will retry automatically."
          />
        </Card>
      ) : (
        <div className="space-y-6">
          <IndexStrip pulse={data} />

          <div className="grid gap-6 lg:grid-cols-3">
            <BreadthCard breadth={data.breadth} />
            <FlowsCard flows={data.institutional_flows} />
            <GlobalCues cues={data.global} />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <SectorBars sectors={data.sectors} />
            </div>
            <MoversCard title="Near 52-week highs" stocks={data.near_year_high.slice(0, 8)} icon="rocket" showRange />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <MoversCard title="Top gainers · F&O" stocks={data.gainers} icon="trendUp" />
            <MoversCard title="Top losers · F&O" stocks={data.losers} icon="trendDown" />
          </div>

          <p className="text-center text-[11px] text-slate-400 dark:text-slate-500">
            Delayed quotes from Yahoo Finance; F&O list, market caps and FII/DII from NSE.{" "}
            {data.universe.source === "nse"
              ? `F&O list as of ${data.universe.trade_date}.`
              : "F&O list is the built-in one until the first NSE snapshot."}{" "}
            Session status follows the clock; exchange holidays are not shown.
          </p>
        </div>
      )}
    </div>
  );
}
