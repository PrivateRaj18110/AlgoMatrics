// TanStack Query hooks over the typed API client. Query keys embed the active
// organization so switching tenants transparently swaps cached data.

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuth } from "@/stores/auth";
import type {
  AdminCoupon,
  AdminOrganization,
  AdminUser,
  AppNotification,
  AuditEntry,
  AuditFilters,
  BrokerCatalogEntry,
  FeatureFlag,
  MarketplaceLicense,
  MarketplaceListing,
  BrokerConnection,
  BuiltinManifest,
  CheckoutResponse,
  CouponPreview,
  DailyPnl,
  DashboardSummary,
  EquityPoint,
  Exposure,
  Instrument,
  Invitation,
  Invoice,
  KillSwitch,
  Member,
  MonthlyPnl,
  NotificationPreference,
  Order,
  Paged,
  Payment,
  PerformanceSummary,
  Plan,
  PlacedOrder,
  Position,
  Quote,
  RiskEvent,
  RiskLimits,
  Strategy,
  StrategyLog,
  StrategyRun,
  StrategyVersion,
  Subscription,
  SystemHealth,
  Trade,
  TradingAccount,
  Usage,
  UserProfile,
  VenueInstrument,
  Watchlist,
} from "@/types/api";

function orgKey(): string {
  return useAuth.getState().activeOrgId ?? "none";
}

/* --------------------------------- account ---------------------------------- */

export function useProfile() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api<UserProfile>("/me", { skipOrg: true }),
  });
}

/* ------------------------------- organizations ------------------------------ */

export function useMembers() {
  return useQuery({
    queryKey: ["members", orgKey()],
    queryFn: () => api<Member[]>("/members"),
  });
}

export function useInvitations() {
  return useQuery({
    queryKey: ["invitations", orgKey()],
    queryFn: () => api<Invitation[]>("/members/invitations"),
  });
}

/* ---------------------------------- billing --------------------------------- */

export function usePlans() {
  return useQuery({
    queryKey: ["plans"],
    queryFn: () => api<Plan[]>("/billing/plans", { skipOrg: true }),
  });
}

export function useSubscription() {
  return useQuery({
    queryKey: ["subscription", orgKey()],
    queryFn: () => api<Subscription>("/billing/subscription"),
  });
}

export function useInvoices() {
  return useQuery({
    queryKey: ["invoices", orgKey()],
    queryFn: () => api<Invoice[]>("/billing/invoices", { query: { limit: 100 } }),
  });
}

export function usePayments() {
  return useQuery({
    queryKey: ["payments", orgKey()],
    queryFn: () => api<Payment[]>("/billing/payments", { query: { limit: 100 } }),
  });
}

export function useUsage() {
  return useQuery({
    queryKey: ["usage", orgKey()],
    queryFn: () => api<Usage>("/billing/usage"),
  });
}

export function useCheckout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      plan_code: string;
      cycle: "monthly" | "yearly";
      provider?: string | null;
      coupon_code?: string | null;
      use_trial?: boolean;
    }) => api<CheckoutResponse>("/billing/checkout", { method: "POST", body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["subscription"] });
      client.invalidateQueries({ queryKey: ["invoices"] });
    },
  });
}

export function usePreviewCoupon() {
  return useMutation({
    mutationFn: (body: { code: string; plan_code: string; cycle: "monthly" | "yearly" }) =>
      api<CouponPreview>("/billing/coupons/preview", { method: "POST", body }),
  });
}

/* --------------------------------- brokers ---------------------------------- */

export function useBrokerCatalog() {
  return useQuery({
    queryKey: ["broker-catalog", orgKey()],
    queryFn: () => api<BrokerCatalogEntry[]>("/brokers"),
  });
}

export function useBrokerConnections() {
  return useQuery({
    queryKey: ["broker-connections", orgKey()],
    queryFn: () => api<BrokerConnection[]>("/broker-connections"),
  });
}

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts", orgKey()],
    queryFn: () => api<TradingAccount[]>("/accounts"),
  });
}

/* --------------------------------- market ----------------------------------- */

export function useInstruments(search?: string) {
  return useQuery({
    queryKey: ["instruments", orgKey(), search ?? ""],
    queryFn: () =>
      api<Instrument[]>("/market-data/instruments", {
        query: { q: search, limit: 200 },
      }),
    placeholderData: keepPreviousData,
  });
}

export function useScanner(sort: "gainers" | "losers" | "active" = "active") {
  return useQuery({
    queryKey: ["scanner", orgKey(), sort],
    queryFn: () =>
      api<import("@/types/api").ScannerRow[]>("/market-data/scanner", {
        query: { sort, limit: 8 },
      }),
    refetchInterval: 10000,
  });
}

export function useQuotes(instrumentIds: string[], enabled = true) {
  return useQuery({
    queryKey: ["quotes", orgKey(), instrumentIds.join(",")],
    queryFn: () =>
      api<Quote[]>("/market-data/quotes", {
        query: { instrument_ids: instrumentIds.join(",") },
      }),
    enabled: enabled && instrumentIds.length > 0,
    refetchInterval: 5000,
  });
}

/* --------------------------------- trading ---------------------------------- */

export function useOrders(params: {
  account_id?: string;
  status?: string;
  open_only?: boolean;
} = {}) {
  return useQuery({
    queryKey: ["orders", orgKey(), params],
    queryFn: () => api<Paged<Order>>("/orders", { query: { ...params, limit: 100 } }),
    refetchInterval: 8000,
  });
}

export function useTrades(params: { account_id?: string } = {}) {
  return useQuery({
    queryKey: ["trades", orgKey(), params],
    queryFn: () => api<Paged<Trade>>("/trades", { query: { ...params, limit: 100 } }),
  });
}

export function usePositions(params: { account_id?: string } = {}) {
  return useQuery({
    queryKey: ["positions", orgKey(), params],
    queryFn: () => api<Position[]>("/positions", { query: params }),
    refetchInterval: 8000,
  });
}

export function usePlaceOrder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<PlacedOrder>("/orders", { method: "POST", body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orders"] });
      client.invalidateQueries({ queryKey: ["positions"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useCancelOrder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (orderId: string) =>
      api<PlacedOrder>(`/orders/${orderId}/cancel`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["orders"] }),
  });
}

export function useWatchlists() {
  return useQuery({
    queryKey: ["watchlists", orgKey()],
    queryFn: () => api<Watchlist[]>("/watchlists"),
  });
}

export function useCreateWatchlist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      api<Watchlist>("/watchlists", { method: "POST", body: { name } }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

export function useRenameWatchlist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ watchlistId, name }: { watchlistId: string; name: string }) =>
      api<Watchlist>(`/watchlists/${watchlistId}`, { method: "PATCH", body: { name } }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

export function useDeleteWatchlist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (watchlistId: string) =>
      api<{ message: string }>(`/watchlists/${watchlistId}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

export function useAddWatchlistItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ watchlistId, instrumentId }: { watchlistId: string; instrumentId: string }) =>
      api<Watchlist>(`/watchlists/${watchlistId}/items`, {
        method: "POST",
        body: { instrument_id: instrumentId },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

export function useRemoveWatchlistItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ watchlistId, itemId }: { watchlistId: string; itemId: string }) =>
      api<Watchlist>(`/watchlists/${watchlistId}/items/${itemId}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}

/* ---------------------------------- risk ------------------------------------ */

export function useRiskLimits() {
  return useQuery({
    queryKey: ["risk-limits", orgKey()],
    queryFn: () => api<RiskLimits[]>("/risk/limits"),
  });
}

export function useKillSwitches() {
  return useQuery({
    queryKey: ["kill-switches", orgKey()],
    queryFn: () => api<KillSwitch[]>("/risk/kill-switches"),
  });
}

export function useRiskViolations() {
  return useQuery({
    queryKey: ["risk-violations", orgKey()],
    queryFn: () =>
      api<{ items: RiskEvent[]; total: number }>("/risk/violations", {
        query: { limit: 100 },
      }),
  });
}

/* -------------------------------- strategies -------------------------------- */

export function useStrategies() {
  return useQuery({
    queryKey: ["strategies", orgKey()],
    queryFn: () => api<Strategy[]>("/strategies"),
  });
}

export function useBuiltinStrategies() {
  return useQuery({
    queryKey: ["builtin-strategies", orgKey()],
    queryFn: () => api<BuiltinManifest[]>("/strategies/builtin"),
  });
}

export function useStrategyVersions(strategyId: string | undefined) {
  return useQuery({
    queryKey: ["strategy-versions", orgKey(), strategyId],
    queryFn: () => api<StrategyVersion[]>(`/strategies/${strategyId}/versions`),
    enabled: Boolean(strategyId),
  });
}

export function useStrategyRuns(params: { strategy_id?: string; active_only?: boolean } = {}) {
  return useQuery({
    queryKey: ["strategy-runs", orgKey(), params],
    queryFn: () => api<StrategyRun[]>("/strategy-runs", { query: params }),
    refetchInterval: 10000,
  });
}

export function useStrategyRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["strategy-run", orgKey(), runId],
    queryFn: () => api<StrategyRun>(`/strategy-runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}

export function useStrategyLogs(runId: string | undefined) {
  return useQuery({
    queryKey: ["strategy-logs", orgKey(), runId],
    queryFn: () => api<StrategyLog[]>(`/strategy-runs/${runId}/logs`, { query: { limit: 200 } }),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}

/* ------------------------------- dashboard ---------------------------------- */

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard", orgKey()],
    queryFn: () => api<DashboardSummary>("/dashboard/summary"),
    refetchInterval: 10000,
  });
}

export function useEquityCurve(days = 30) {
  return useQuery({
    queryKey: ["equity-curve", orgKey(), days],
    queryFn: () => api<EquityPoint[]>("/portfolio/equity-curve", { query: { days } }),
  });
}

export function useDailyPnl(days = 90) {
  return useQuery({
    queryKey: ["daily-pnl", orgKey(), days],
    queryFn: () => api<DailyPnl[]>("/analytics/daily-pnl", { query: { days } }),
  });
}

export function useMonthlyPnl(months = 12) {
  return useQuery({
    queryKey: ["monthly-pnl", orgKey(), months],
    queryFn: () => api<MonthlyPnl[]>("/analytics/monthly-pnl", { query: { months } }),
  });
}

export function usePerformance(days = 90) {
  return useQuery({
    queryKey: ["performance", orgKey(), days],
    queryFn: () => api<PerformanceSummary>("/analytics/summary", { query: { days } }),
  });
}

export function useExposure() {
  return useQuery({
    queryKey: ["exposure", orgKey()],
    queryFn: () => api<Exposure[]>("/analytics/exposure"),
    refetchInterval: 10000,
  });
}

/* ------------------------------ notifications ------------------------------- */

export function useNotifications() {
  return useQuery({
    queryKey: ["notifications", orgKey()],
    queryFn: () => api<AppNotification[]>("/notifications", { query: { limit: 50 } }),
    refetchInterval: 20000,
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: ["notifications-unread", orgKey()],
    queryFn: () => api<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 20000,
  });
}

function invalidateNotifications(client: ReturnType<typeof useQueryClient>): void {
  client.invalidateQueries({ queryKey: ["notifications"] });
  client.invalidateQueries({ queryKey: ["notifications-unread"] });
}

export function useMarkNotificationRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      api<{ message: string }>(`/notifications/${notificationId}/read`, { method: "POST" }),
    onSuccess: () => invalidateNotifications(client),
  });
}

export function useMarkAllNotificationsRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ message: string }>("/notifications/read-all", { method: "POST" }),
    onSuccess: () => invalidateNotifications(client),
  });
}

export function useNotificationPreferences() {
  return useQuery({
    queryKey: ["notification-preferences", orgKey()],
    queryFn: () => api<NotificationPreference>("/notifications/preferences"),
  });
}

export function useUpdateNotificationPreferences() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: NotificationPreference) =>
      api<NotificationPreference>("/notifications/preferences", { method: "PUT", body }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["notification-preferences"] }),
  });
}

/* ---------------------------------- audit ----------------------------------- */

export function useAuditEvents(filters: AuditFilters = {}) {
  const { actionPrefix, correlationId, resourceType, occurredFrom, occurredTo } = filters;
  return useQuery({
    queryKey: [
      "audit",
      orgKey(),
      actionPrefix ?? "",
      correlationId ?? "",
      resourceType ?? "",
      occurredFrom ?? "",
      occurredTo ?? "",
    ],
    queryFn: () =>
      api<{ items: AuditEntry[]; total: number }>("/audit-events", {
        query: {
          limit: 100,
          action_prefix: actionPrefix,
          correlation_id: correlationId,
          resource_type: resourceType,
          occurred_from: occurredFrom,
          occurred_to: occurredTo,
        },
      }),
  });
}

/* ----------------------------------- ai ------------------------------------- */

export interface AiAnswer {
  answer: string;
  provider: string;
}

export function useAiAssistant() {
  return useMutation({
    mutationFn: (question: string) =>
      api<AiAnswer>("/ai/assistant", { method: "POST", body: { question } }),
  });
}

/* ------------------------------- backtesting -------------------------------- */

export interface BacktestBar {
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface BacktestResult {
  id: string;
  total_return_pct: number;
  max_drawdown_pct: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  annualized_return_pct: number;
  trades: number;
  win_rate_pct: number;
  ending_equity: number;
}

export function useSignalTypes() {
  return useQuery({
    queryKey: ["backtest-signal-types"],
    queryFn: () => api<string[]>("/backtests/signal-types"),
    staleTime: 300_000,
  });
}

export function useRunBacktest() {
  return useMutation({
    mutationFn: (body: {
      signal_type: string;
      params: Record<string, number>;
      bars: BacktestBar[];
    }) => api<BacktestResult>("/backtests/run", { method: "POST", body }),
  });
}

/* ------------------------------- marketplace -------------------------------- */

export function useMarketplaceListings() {
  return useQuery({
    queryKey: ["marketplace", orgKey()],
    queryFn: () => api<MarketplaceListing[]>("/marketplace/listings", { query: { limit: 100 } }),
  });
}

export function useMyLicenses() {
  return useQuery({
    queryKey: ["marketplace-licenses", orgKey()],
    queryFn: () => api<MarketplaceLicense[]>("/marketplace/licenses"),
  });
}

export function useAcquireLicense() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (listingId: string) =>
      api<MarketplaceLicense>(`/marketplace/listings/${listingId}/license`, { method: "POST" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["marketplace-licenses"] });
      client.invalidateQueries({ queryKey: ["marketplace"] });
    },
  });
}

/* ------------------------------ feature flags ------------------------------- */

export function useFeatureFlags() {
  return useQuery({
    queryKey: ["feature-flags", orgKey()],
    queryFn: () => api<Record<string, boolean>>("/feature-flags"),
    staleTime: 60_000,
  });
}

export function useAdminFeatureFlags() {
  return useQuery({
    queryKey: ["admin-feature-flags"],
    queryFn: () => api<FeatureFlag[]>("/admin/feature-flags"),
  });
}

export function useUpsertFeatureFlag() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ key, ...body }: FeatureFlag) =>
      api<FeatureFlag>(`/admin/feature-flags/${key}`, { method: "PUT", body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["admin-feature-flags"] });
      client.invalidateQueries({ queryKey: ["feature-flags"] });
    },
  });
}

/* ---------------------------------- admin ----------------------------------- */

export function useAdminUsers(search?: string) {
  return useQuery({
    queryKey: ["admin-users", search ?? ""],
    queryFn: () => api<AdminUser[]>("/admin/users", { query: { q: search, limit: 100 } }),
  });
}

export function useAdminOrganizations() {
  return useQuery({
    queryKey: ["admin-organizations"],
    queryFn: () => api<AdminOrganization[]>("/admin/organizations", { query: { limit: 100 } }),
  });
}

export function useAdminPlans() {
  return useQuery({
    queryKey: ["admin-plans"],
    queryFn: () => api<Plan[]>("/admin/plans"),
  });
}

export function useAdminCoupons() {
  return useQuery({
    queryKey: ["admin-coupons"],
    queryFn: () => api<AdminCoupon[]>("/admin/coupons"),
  });
}

export function useSystemHealth() {
  return useQuery({
    queryKey: ["system-health"],
    queryFn: () => api<SystemHealth>("/admin/health"),
    refetchInterval: 15000,
  });
}

export function useAdminMetrics() {
  return useQuery({
    queryKey: ["admin-metrics"],
    queryFn: () => api<Record<string, number>>("/admin/metrics"),
    refetchInterval: 30000,
  });
}

export function useBrokerMonitor() {
  return useQuery({
    queryKey: ["admin-broker-monitor"],
    queryFn: () => api<Record<string, number>>("/admin/broker-connections"),
  });
}

export function useAdminVenueInstruments() {
  return useQuery({
    queryKey: ["admin-venue-instruments"],
    queryFn: () =>
      api<VenueInstrument[]>("/admin/venue-instruments", {
        query: { include_inactive: true },
        skipOrg: true,
      }),
  });
}
