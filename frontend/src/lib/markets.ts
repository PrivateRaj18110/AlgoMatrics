// Live Indian market data: NSE F&O universe, pre-open screens, market pulse.
// Every number here comes from the backend's market_insights module (NSE +
// Yahoo). Missing values stay null and render as UNKNOWN / "—", never 0.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuth } from "@/stores/auth";

export interface MarketSession {
  state: "open" | "pre_open" | "closed";
  as_of: string;
  note: string;
}

export interface Breadth {
  advances: number;
  declines: number;
  unchanged: number;
  ratio: number | null;
  pct_advancing: number | null;
  near_year_high: number;
  near_year_low: number;
}

export interface QuoteRow {
  symbol: string;
  name: string;
  price: number | null;
  previous_close: number | null;
  change_pct: number | null;
  day_high: number | null;
  day_low: number | null;
  /** Unix seconds, straight from the source. */
  as_of: number | null;
}

export interface FoStock extends QuoteRow {
  sector: string;
  year_high: number | null;
  year_low: number | null;
  volume: number | null;
  market_cap: number | null;
}

export interface UniverseSource {
  source: "nse" | "built_in";
  trade_date: string | null;
}

export interface FoHeatmap {
  universe: UniverseSource;
  session: MarketSession;
  breadth: Breadth;
  stocks: FoStock[];
  quoted: number;
  total: number;
}

export interface SectorMove {
  sector: string;
  change_pct: number;
  members: number;
  advancing: number;
  leader: string | null;
  laggard: string | null;
}

export interface TrendRegime {
  label: "Uptrend" | "Downtrend" | "Range-bound" | "Unknown";
  price: number | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  rsi14: number | null;
  return_5d: number | null;
  return_20d: number | null;
  explanation: string;
}

export interface InstitutionalFlow {
  trade_date: string;
  fii_net: number | null;
  dii_net: number | null;
  fii_buy: number | null;
  fii_sell: number | null;
  dii_buy: number | null;
  dii_sell: number | null;
}

export interface MarketPulse {
  session: MarketSession;
  universe: UniverseSource;
  indices: QuoteRow[];
  vix: QuoteRow;
  global: Array<QuoteRow & { region: string }>;
  breadth: Breadth;
  sectors: SectorMove[];
  gainers: FoStock[];
  losers: FoStock[];
  near_year_high: FoStock[];
  regime: {
    nifty: TrendRegime;
    bank_nifty: TrendRegime;
    volatility: { label: string; vix: number | null; explanation: string };
  };
  institutional_flows: InstitutionalFlow[];
}

export interface PremarketPick {
  symbol: string;
  sector: string;
  iep: number;
  change_pct: number;
  imbalance: number;
  turnover: number;
  score: number;
  bias: "long" | "short" | "watch";
  reasons: string[];
}

export interface PremarketScreen {
  key: string;
  title: string;
  description: string;
  picks: PremarketPick[];
}

export interface PremarketStock {
  symbol: string;
  sector: string;
  iep: number;
  previous_close: number;
  change_pct: number;
  imbalance: number;
  buy_quantity: number;
  sell_quantity: number;
  final_quantity: number;
  turnover: number;
  market_cap: number;
  year_high: number | null;
  year_low: number | null;
}

export type Premarket =
  | { available: false; session: MarketSession; dates: string[] }
  | {
      available: true;
      trade_date: string;
      as_of: string | null;
      fetched_at: string;
      stale: boolean;
      session: MarketSession;
      summary: {
        advances: number;
        declines: number;
        unchanged: number;
        total_traded_value: number;
        stocks: number;
      };
      screens: PremarketScreen[];
      stocks: PremarketStock[];
      disclaimer: string;
      dates: string[];
    };

function useSignedIn(): boolean {
  return useAuth((state) => state.status) === "authenticated";
}

export function useFoHeatmap() {
  const ready = useSignedIn();
  return useQuery({
    queryKey: ["markets", "fo-heatmap"],
    queryFn: () => api<FoHeatmap>("/markets/fo-heatmap", { skipOrg: true }),
    enabled: ready,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useMarketPulse() {
  const ready = useSignedIn();
  return useQuery({
    queryKey: ["markets", "pulse"],
    queryFn: () => api<MarketPulse>("/markets/pulse", { skipOrg: true }),
    enabled: ready,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function usePremarket(date: string | null) {
  const ready = useSignedIn();
  return useQuery({
    queryKey: ["markets", "premarket", date ?? "latest"],
    queryFn: () =>
      api<Premarket>("/markets/premarket", { query: { date: date ?? undefined }, skipOrg: true }),
    enabled: ready,
    refetchInterval: 5 * 60_000,
  });
}

export function useRefreshMarketSnapshot() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (kind: "preopen" | "fii_dii") =>
      api<{ kind: string; trade_date: string | null }>("/admin/markets/refresh", {
        method: "POST",
        query: { kind },
        skipOrg: true,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["markets"] }),
  });
}

/* ------------------------------- formatting -------------------------------- */

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

export function price(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : inr.format(value);
}

export function pctText(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "UNKNOWN";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

/** ₹ crore, the unit Indian market data is quoted in. */
export function crore(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(value / 1e7)} cr`;
}

export function compactNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : compact.format(value);
}

export function unixToIso(seconds: number | null | undefined): string | null {
  return seconds ? new Date(seconds * 1000).toISOString() : null;
}

/** Where a price sits in its 52-week range, 0 (low) .. 1 (high). */
export function rangePosition(stock: {
  price: number | null;
  year_low: number | null;
  year_high: number | null;
}): number | null {
  const { price: value, year_low: low, year_high: high } = stock;
  if (value === null || low === null || high === null || high <= low) return null;
  return Math.min(1, Math.max(0, (value - low) / (high - low)));
}

export function toneClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "text-slate-500 dark:text-slate-400";
  return value > 0 ? "text-profit-600 dark:text-profit-400" : "text-loss-600 dark:text-loss-400";
}

export const SESSION_LABEL: Record<MarketSession["state"], string> = {
  open: "Market open",
  pre_open: "Pre-open session",
  closed: "Market closed",
};
