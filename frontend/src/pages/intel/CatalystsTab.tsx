// AI-CIO · Catalysts: every classified NSE filing on F&O stocks since the last
// close, plus today's exchange events (results dates, F&O ban, ex-dates, large
// deals) and open-interest build-up.

import { clsx } from "clsx";
import { useMemo, useState } from "react";

import { Glyph } from "@/components/icons";
import { Badge, Card, EmptyState, SkeletonRows, Tabs } from "@/components/ui";
import { type Catalyst, useCatalysts, useMarketNews } from "@/lib/movers";

import { CatalystChip, ImpactMeter, istStamp } from "./parts";

const LEVELS = [
  { key: "high", label: "High impact", min: 0.6 },
  { key: "material", label: "Material", min: 0.4 },
  { key: "all", label: "Everything", min: 0.15 },
] as const;

const EVENT_GROUPS: { title: string; categories: string[]; empty: string }[] = [
  { title: "Results due today", categories: ["results_today"], empty: "No F&O company has results scheduled today." },
  { title: "In F&O ban", categories: ["fo_ban"], empty: "No F&O stock is in the ban period." },
  { title: "Ex-dates today", categories: ["ex_adjustment", "ex_dividend"], empty: "No ex-dates today." },
  { title: "Bulk & block deals (last session)", categories: ["large_deal"], empty: "No large deals in F&O stocks." },
  { title: "Board meetings on buybacks / fund raising", categories: ["buyback", "fund_raise"], empty: "None today." },
];

function FilingRow({ item, today }: { item: Catalyst; today: string }) {
  return (
    <li className="grid grid-cols-[3.5rem_minmax(0,1fr)] gap-x-3 py-3 sm:grid-cols-[3.5rem_7rem_minmax(0,1fr)]">
      <span className="pt-0.5 font-data text-xs text-slate-500">{istStamp(item.at, today)}</span>
      <span className="font-semibold text-slate-900 sm:pt-0.5 dark:text-white">{item.symbol}</span>
      <div className="col-span-2 min-w-0 sm:col-span-1">
        <div className="flex flex-wrap items-center gap-2">
          <CatalystChip catalyst={item} />
          <ImpactMeter impact={item.impact} />
          {item.session === "intraday" ? <Badge color="amber">During market hours</Badge> : null}
          {item.session === "after_close" ? <Badge color="blue">After the close · next session</Badge> : null}
        </div>
        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-600 dark:text-slate-300">{item.title}</p>
        {item.note ? (
          <p className="mt-1 flex items-center gap-1 text-[11px] text-violet-600 dark:text-violet-300">
            <Glyph name="bolt" className="size-3" />
            Claude: {item.note}
          </p>
        ) : null}
      </div>
    </li>
  );
}

export function CatalystsTab() {
  const [level, setLevel] = useState<(typeof LEVELS)[number]["key"]>("material");
  const catalysts = useCatalysts(null);
  const data = catalysts.data;
  const min = LEVELS.find((item) => item.key === level)?.min ?? 0.4;
  const filings = useMemo(() => (data?.filings ?? []).filter((item) => item.impact >= min), [data, min]);
  const oi = useMemo(
    () => Object.entries(data?.oi_spurts ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 10),
    [data],
  );

  if (catalysts.isLoading) return <SkeletonRows rows={6} cols={3} />;
  if (!data) {
    return (
      <Card>
        <EmptyState title="Catalysts are unavailable" body="The filings service did not answer; this page retries every two minutes." />
      </Card>
    );
  }
  const today = data.trade_date;

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <Card
        className="xl:col-span-2"
        title="Exchange filings on F&O stocks"
        subtitle={`Since the last close · updated ${istStamp(data.updated_at, today)} IST${data.ai_reader ? " · read by Claude" : ""}`}
        icon={<Glyph name="receipt" className="size-3.5" />}
        actions={<Tabs tabs={LEVELS.map(({ key, label }) => ({ key, label }))} active={level} onChange={(key) => setLevel(key as typeof level)} />}
      >
        {filings.length === 0 ? (
          <EmptyState
            title="Nothing at this level yet"
            body="Filings are checked every few minutes from 06:30 to 22:30 IST on trading days. Try a lower impact level."
          />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-white/[0.05]">
            {filings.map((item) => (
              <FilingRow key={item.id} item={item} today={today} />
            ))}
          </ul>
        )}
      </Card>

      <div className="space-y-6">
        <Card title="Today on the exchange" subtitle={`Updated ${istStamp(data.events_updated_at, today)} IST`} icon={<Glyph name="clock" className="size-3.5" />}>
          <div className="space-y-4">
            {EVENT_GROUPS.map((group) => {
              const items = data.events.filter((item) => group.categories.includes(item.category));
              return (
                <section key={group.title}>
                  <h3 className="mb-1.5 text-[11px] font-semibold tracking-wide text-slate-500 uppercase">{group.title}</h3>
                  {items.length === 0 ? (
                    <p className="text-xs text-slate-400">{group.empty}</p>
                  ) : (
                    <ul className="space-y-1">
                      {items.slice(0, 12).map((item) => (
                        <li key={item.id} className="flex items-baseline gap-2 text-xs">
                          <span className="w-24 shrink-0 font-semibold text-slate-900 dark:text-white">{item.symbol}</span>
                          <span className={clsx("min-w-0 truncate", item.direction > 0 ? "text-profit-600 dark:text-profit-400" : item.direction < 0 ? "text-loss-600 dark:text-loss-400" : "text-slate-500")} title={item.title}>
                            {item.title || item.label}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>
        </Card>

        <Card title="Open-interest build-up" subtitle="Largest rise in F&O open interest, last session" icon={<Glyph name="layers" className="size-3.5" />}>
          {oi.length === 0 ? (
            <p className="text-xs text-slate-400">No open-interest data for today yet (published by NSE during the session).</p>
          ) : (
            <ul className="space-y-1.5">
              {oi.map(([symbol, change]) => (
                <li key={symbol} className="flex items-center gap-3 text-xs">
                  <span className="w-24 font-semibold text-slate-900 dark:text-white">{symbol}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-white/[0.08]">
                    <div className="h-full rounded-full bg-violet-500" style={{ width: `${Math.min(100, change)}%` }} />
                  </div>
                  <span className="w-14 text-right font-data tabular-nums text-slate-700 dark:text-slate-200">+{change.toFixed(0)}%</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

export function NewsTab() {
  const [taggedOnly, setTaggedOnly] = useState(true);
  const news = useMarketNews(null, taggedOnly);
  const data = news.data;

  if (news.isLoading) return <SkeletonRows rows={6} cols={2} />;
  if (!data) {
    return (
      <Card>
        <EmptyState title="Headlines are unavailable" body="The news service did not answer; this page retries every five minutes." />
      </Card>
    );
  }
  return (
    <Card
      title="Market headlines since the last close"
      subtitle={`Economic Times, Mint, Business Standard and Google News · titles and links only · updated ${istStamp(data.updated_at, data.trade_date)} IST`}
      icon={<Glyph name="inbox" className="size-3.5" />}
      actions={
        <Tabs
          tabs={[
            { key: "tagged", label: "Naming an F&O stock" },
            { key: "all", label: "All headlines" },
          ]}
          active={taggedOnly ? "tagged" : "all"}
          onChange={(key) => setTaggedOnly(key === "tagged")}
        />
      }
    >
      {data.items.length === 0 ? (
        <EmptyState title="No headlines yet" body="Feeds are read every 15 minutes from 06:30 to 22:30 IST on trading days." />
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-white/[0.05]">
          {data.items.map((item) => (
            <li key={item.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5">
              <span className="w-12 shrink-0 pt-0.5 font-data text-xs text-slate-500">{istStamp(item.at, data.trade_date)}</span>
              <div className="min-w-0 flex-1">
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer noopener" className="text-sm text-slate-800 hover:text-accent-600 dark:text-slate-100 dark:hover:text-accent-300">
                    {item.title}
                  </a>
                ) : (
                  <p className="text-sm text-slate-800 dark:text-slate-100">{item.title}</p>
                )}
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
                  {item.source}
                  {item.symbols.map((symbol) => (
                    <span key={symbol} className="rounded bg-slate-100 px-1.5 py-px font-semibold text-slate-700 dark:bg-white/[0.06] dark:text-slate-200">
                      {symbol}
                    </span>
                  ))}
                  {item.sentiment !== 0 ? (
                    <span className={item.sentiment > 0 ? "text-profit-600 dark:text-profit-400" : "text-loss-600 dark:text-loss-400"}>
                      {item.sentiment > 0 ? "▲ positive tone" : "▼ negative tone"}
                    </span>
                  ) : null}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
