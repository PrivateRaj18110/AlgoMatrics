// AI-CIO movers radar: which F&O stocks are likely to make a major move today,
// the filings and headlines behind it, and how the forecasts have graded.
// Everything comes from /markets/movers*, /markets/catalysts and /markets/news.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuth } from "@/stores/auth";

export type MoveDirection = "up" | "down" | "either";
export type ForecastStage = "overnight" | "opening";

export interface Catalyst {
  id: string;
  symbol: string;
  source: string;
  category: string;
  label: string;
  impact: number;
  direction: -1 | 0 | 1;
  title: string;
  at: string | null;
  url: string | null;
  company: string | null;
  note?: string | null;
  session?: "overnight" | "intraday" | "after_close";
}

export interface ForecastReason {
  feature: string;
  text: string;
  weight: number;
}

export interface ForecastStock {
  symbol: string;
  sector: string;
  rank: number;
  probability: number;
  direction: MoveDirection;
  direction_basis: string;
  direction_confidence: "high" | "medium" | "low";
  gap_pct: number | null;
  imbalance: number | null;
  typical_move_pct: number;
  threshold_pct: number;
  prev_change_pct: number | null;
  last_close: number | null;
  news_count: number;
  oi_change_pct: number | null;
  reasons: ForecastReason[];
  catalysts: Catalyst[];
  flags: { results: boolean; ban: boolean; ex_adjustment: boolean };
}

export interface ModelMeta {
  source: "prior" | "fitted";
  version: string | null;
  fitted_at: string | null;
  samples?: Record<ForecastStage, number>;
  days?: number;
  fitted_on?: string;
}

export interface Forecast {
  stage: ForecastStage;
  trade_date: string;
  generated_at: string;
  model: ModelMeta;
  universe: number;
  expected_majors: number;
  threshold_rule: string;
  stocks: ForecastStock[];
}

export interface DayGrade {
  top_k: number;
  hits: number;
  majors: number;
  universe: number;
  precision: number | null;
  base_rate: number | null;
  recall: number | null;
  lift: number | null;
  direction_calls: number;
  direction_right: number;
  brier: number | null;
  hit_symbols: string[];
  missed_symbols: string[];
}

export interface DayOutcome {
  evaluated_at: string;
  /** symbol → [% change close to close, was it a major move] */
  stocks: Record<string, [number, boolean]>;
  grades: Partial<Record<ForecastStage, DayGrade>>;
}

export type Movers =
  | { available: false; model: ModelMeta; dates: string[]; disclaimer: string }
  | {
      available: true;
      trade_date: string;
      stage: ForecastStage;
      stale: boolean;
      forecast: Forecast;
      overnight_available: boolean;
      outcome: DayOutcome | null;
      intraday: Catalyst[];
      model: ModelMeta;
      dates: string[];
      disclaimer: string;
    };

export interface Catalysts {
  trade_date: string;
  filings: Catalyst[];
  events: Catalyst[];
  oi_spurts: Record<string, number>;
  updated_at: string | null;
  events_updated_at: string | null;
  ai_reader: boolean;
}

export interface Headline {
  id: string;
  title: string;
  source: string;
  url: string | null;
  at: string | null;
  symbols: string[];
  sentiment: -1 | 0 | 1;
}

export interface MarketNews {
  trade_date: string;
  items: Headline[];
  feeds: number | null;
  updated_at: string | null;
}

export interface PooledGrade {
  days: number;
  top_k_picks: number;
  hits: number;
  precision: number | null;
  base_rate: number | null;
  lift: number | null;
  recall: number | null;
  direction_accuracy: number | null;
  direction_calls: number;
  brier: number | null;
}

export interface CalibrationBand {
  band: string;
  count: number;
  predicted: number;
  actual: number;
}

export interface GradedDay extends DayGrade {
  day: string;
}

export interface BacktestStage {
  weights_on_train: { bias: number; weights: Record<string, number> };
  fitted: { summary: PooledGrade; daily: GradedDay[] };
  prior: { summary: PooledGrade; daily: GradedDay[] };
  calibration?: CalibrationBand[];
}

export interface Backtest {
  ran_on: string;
  ran_at: string;
  sessions: number;
  train: [string, string] | null;
  test: [string, string] | null;
  universe: number;
  filings: number;
  base_rate: number | null;
  stages: Record<ForecastStage, BacktestStage>;
  limits: string[];
}

export interface ModelFeature {
  name: string;
  label: string;
  opening_only: boolean;
  prior: Record<ForecastStage, number>;
  weight: Record<ForecastStage, number>;
}

export interface TrackRecord {
  live: Record<ForecastStage, { summary: PooledGrade; daily: GradedDay[] }>;
  calibration: CalibrationBand[];
  backtest: Backtest | null;
  model: ModelMeta & {
    features: ModelFeature[];
    bias: Record<ForecastStage, number>;
    prior_bias: Record<ForecastStage, number>;
    top_k: number;
    threshold_rule: string;
  };
  disclaimer: string;
}

function useSignedIn(): boolean {
  return useAuth((state) => state.status) === "authenticated";
}

export function useMovers(date: string | null) {
  const ready = useSignedIn();
  return useQuery({
    queryKey: ["markets", "movers", date ?? "latest"],
    queryFn: () => api<Movers>("/markets/movers", { query: { date: date ?? undefined }, skipOrg: true }),
    enabled: ready,
    refetchInterval: 2 * 60_000,
  });
}

export function useMoversTrackRecord() {
  const ready = useSignedIn();
  return useQuery({
    queryKey: ["markets", "movers-track-record"],
    queryFn: () => api<TrackRecord>("/markets/movers/track-record", { skipOrg: true }),
    enabled: ready,
    staleTime: 5 * 60_000,
  });
}

export function useCatalysts(date: string | null, minImpact = 0.15) {
  const ready = useSignedIn();
  return useQuery({
    queryKey: ["markets", "catalysts", date ?? "latest", minImpact],
    queryFn: () =>
      api<Catalysts>("/markets/catalysts", {
        query: { date: date ?? undefined, min_impact: minImpact },
        skipOrg: true,
      }),
    enabled: ready,
    refetchInterval: 2 * 60_000,
  });
}

export function useMarketNews(date: string | null, taggedOnly: boolean) {
  const ready = useSignedIn();
  return useQuery({
    queryKey: ["markets", "news", date ?? "latest", taggedOnly],
    queryFn: () =>
      api<MarketNews>("/markets/news", {
        query: { date: date ?? undefined, tagged: taggedOnly || undefined },
        skipOrg: true,
      }),
    enabled: ready,
    refetchInterval: 5 * 60_000,
  });
}

export type MoversJob = "filings" | "events" | "news" | "forecast" | "grade" | "backtest";

export function useRunMoversJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (job: MoversJob) =>
      api<Record<string, unknown>>("/admin/markets/movers", { method: "POST", query: { job }, skipOrg: true }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["markets"] }),
  });
}

/* ------------------------------ morning briefing ----------------------------- */

export interface StoredBriefing {
  day: string;
  sent_at: string;
  subject: string;
  stage: ForecastStage | null;
  recipients: string[];
  delivery: string;
  text: string;
  html: string;
}

export interface BriefingArchive {
  dates: string[];
  briefing: StoredBriefing | null;
  delivery: "console" | "smtp";
  enabled: boolean;
}

/** Owner only: the stored morning briefings (the daily log). */
export function useBriefingArchive(date: string | null) {
  return useQuery({
    queryKey: ["markets", "briefing", date ?? "latest"],
    queryFn: () =>
      api<BriefingArchive>("/admin/markets/briefing", { query: { date: date ?? undefined }, skipOrg: true }),
  });
}

/** Preview (send=false) or send and log (send=true) today's briefing now. */
export function useBriefingAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (send: boolean) =>
      api<{ day: string; subject: string; html: string; recipients?: string[] }>("/admin/markets/briefing", {
        method: "POST",
        query: { send },
        skipOrg: true,
      }),
    onSuccess: (_data, send) => {
      if (send) void client.invalidateQueries({ queryKey: ["markets", "briefing"] });
    },
  });
}

/* ------------------------------- formatting -------------------------------- */

export function chance(probability: number | null | undefined): string {
  if (probability === null || probability === undefined || !Number.isFinite(probability)) return "—";
  const pct = probability * 100;
  return pct < 1 ? "<1%" : `${pct.toFixed(pct < 10 ? 1 : 0)}%`;
}

export function ratio(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function signedPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export const DIRECTION_LABEL: Record<MoveDirection, string> = {
  up: "Likely up",
  down: "Likely down",
  either: "Either way",
};

export const STAGE_LABEL: Record<ForecastStage, string> = {
  overnight: "Overnight forecast",
  opening: "Opening forecast",
};
