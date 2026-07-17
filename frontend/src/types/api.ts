// API contract types mirroring the backend response schemas (/api/v1).

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  status: string;
  email_verified: boolean;
  mfa_enabled: boolean;
  avatar_url: string | null;
  timezone: string;
  theme: "dark" | "light" | "system";
  preferences: Record<string, unknown>;
  notification_settings: Record<string, boolean>;
  is_platform_admin: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Tokens {
  access_token: string;
  access_expires_at: string;
  refresh_token: string | null;
  refresh_expires_at: string;
  session_id: string;
  user: UserProfile;
}

export interface LoginResponse {
  kind: "tokens" | "mfa_required";
  tokens: Tokens | null;
  mfa_token: string | null;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: string;
  settings: Record<string, unknown>;
  created_at: string;
}

export interface Member {
  membership_id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  invited_by: string;
  expires_at: string;
  created_at: string;
}

export interface SessionInfo {
  id: string;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface CreatedApiKey {
  key: ApiKey;
  secret: string;
}

export interface MfaEnrollment {
  secret: string;
  provisioning_uri: string;
}

export interface Plan {
  id: string;
  code: string;
  name: string;
  description: string;
  price_monthly: string;
  price_yearly: string;
  currency: string;
  features: string[];
  trial_days: number;
  is_active: boolean;
  sort_order: number;
  limits?: Record<string, unknown>;
  provider_prices?: Record<string, string>;
}

export interface Subscription {
  id: string;
  status: string;
  plan_code: string;
  plan_name: string;
  billing_cycle: string;
  price_monthly: string;
  price_yearly: string;
  currency: string;
  current_period_start: string;
  current_period_end: string;
  trial_end: string | null;
  trial_available: boolean;
  cancel_at_period_end: boolean;
  limits: Record<string, unknown>;
  features: string[];
  provider: string | null;
  provider_status: string | null;
}

export interface CheckoutResponse {
  kind: string;
  message: string;
  invoice_id: string | null;
  provider: string | null;
  checkout_url: string | null;
  payload: Record<string, unknown>;
}

export interface CouponPreview {
  code: string;
  description: string;
  discount: string;
  subtotal: string;
  total: string;
  currency: string;
}

export interface Invoice {
  id: string;
  number: string;
  status: string;
  currency: string;
  subtotal: string;
  discount: string;
  total: string;
  line_items: Array<Record<string, unknown>>;
  period_start: string;
  period_end: string;
  coupon_code: string | null;
  provider: string | null;
  issued_at: string;
  paid_at: string | null;
}

export interface Payment {
  id: string;
  invoice_id: string;
  provider: string;
  provider_payment_id: string;
  amount: string;
  currency: string;
  status: string;
  method: string | null;
  error: string | null;
  captured_at: string | null;
  created_at: string;
}

export interface Usage {
  limits: Record<string, unknown>;
  usage: Record<string, number>;
}

export interface CredentialField {
  name: string;
  label: string;
  secret: boolean;
  help_text?: string;
}

export interface BrokerCatalogEntry {
  id: string;
  code: string;
  name: string;
  description: string;
  credential_fields: CredentialField[];
  capabilities: Record<string, unknown>;
  supports_paper: boolean;
  supports_live: boolean;
}

export interface TradingAccount {
  id: string;
  connection_id: string;
  external_account_id: string;
  name: string;
  mode: "paper" | "live";
  base_currency: string;
  cash_balance: string;
  starting_balance: string;
  equity: string;
  status: string;
}

export interface BrokerConnection {
  id: string;
  broker_code: string;
  broker_name: string;
  name: string;
  status: string;
  last_verified_at: string | null;
  failure_reason: string | null;
  created_at: string;
  accounts: TradingAccount[];
}

export interface Instrument {
  id: string;
  symbol: string;
  name: string;
  exchange: string;
  asset_class: string;
  currency: string;
  tick_size: string;
  lot_size: string;
  price_precision: number;
  is_active: boolean;
}

export interface VenueInstrument {
  id: string;
  broker_id: string;
  instrument_id: string;
  canonical_symbol: string;
  venue_symbol: string;
  exchange: string;
  instrument_token: string | null;
  tick_size: string;
  lot_size: string;
  contract_multiplier: string;
  venue_metadata: Record<string, string>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Quote {
  instrument_id: string;
  symbol: string;
  bid: string | null;
  ask: string | null;
  last: string | null;
  change_pct: string | null;
  timestamp: string | null;
}

export interface ScannerRow {
  instrument_id: string;
  symbol: string;
  name: string;
  asset_class: string;
  last: string | null;
  change_pct: string | null;
}

export interface MarketInfo {
  symbol: string;
  name: string;
  yahoo_symbol: string;
  price: string | null;
  previous_close: string | null;
  change: string | null;
  change_pct: string | null;
  currency: string;
  as_of: string | null;
}

export interface Candle {
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

/* ----------------------------- market intelligence ----------------------------- */
// AI-CIO advisory reads. Numeric fields are JSON numbers (not Decimal strings).

export interface MarketIntelStatus {
  configured: boolean;
}

export interface Regime {
  label: string;
  hmm_confidence: number | null;
  hmm_vol_state: string | null;
  gmm_vol_state: string | null;
  adx_14: number | null;
  avg_pairwise_corr: number | null;
  breadth_pct_above_ma20: number | null;
  days_since_changepoint: number | null;
  as_of: string | null;
}

export interface RankingDimension {
  name: string;
  value: number | null;
}

export interface RankingRow {
  run_date: string;
  ticker: string;
  name: string | null;
  rank: number;
  composite_score: number;
  regime: string;
  dimensions: RankingDimension[];
}

export interface MarketIntelNews {
  ticker: string;
  title: string;
  source: string;
  link: string;
  published_raw: string | null;
  is_duplicate: boolean;
  sentiment_label: string | null;
  sentiment_score: number | null;
}

export interface OptionsSnapshot {
  ticker: string;
  run_date: string;
  max_pain: number | null;
  max_pain_dist_pct: number | null;
  pcr_oi: number | null;
  pcr_volume: number | null;
  iv_skew: number | null;
  atm_iv: number | null;
  oi_score: number | null;
}

export interface InstitutionalBias {
  ticker: string;
  run_date: string;
  net_value: number | null;
  gross_value: number | null;
  n_deals: number | null;
  if_score: number;
}

export interface Order {
  id: string;
  account_id: string;
  instrument_id: string;
  symbol: string;
  side: "buy" | "sell";
  order_type: string;
  time_in_force: string;
  quantity: string;
  limit_price: string | null;
  stop_price: string | null;
  status: string;
  filled_quantity: string;
  average_fill_price: string | null;
  rejection_reason: string | null;
  source: string;
  client_order_id: string;
  strategy_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlacedOrder {
  id: string;
  status: string;
  client_order_id: string;
  rejection_reason: string | null;
}

export interface Trade {
  id: string;
  order_id: string;
  account_id: string;
  instrument_id: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  fee: string;
  fee_currency: string;
  executed_at: string;
}

export interface Position {
  id: string;
  account_id: string;
  instrument_id: string;
  symbol: string;
  side: string;
  quantity: string;
  average_price: string;
  last_mark: string | null;
  market_value: string;
  unrealized_pnl: string;
  realized_pnl: string;
  fees_paid: string;
  updated_at: string;
}

export interface Paged<T> {
  items: T[];
  next_cursor: string | null;
}

export interface WatchlistItem {
  id: string;
  instrument_id: string;
  symbol: string;
  name: string;
  sort_order: number;
}

export interface Watchlist {
  id: string;
  name: string;
  created_at: string;
  items: WatchlistItem[];
}

export interface RiskLimits {
  id: string;
  account_id: string | null;
  max_order_quantity: string;
  max_order_value: string;
  max_daily_loss: string;
  max_open_positions: number;
  max_exposure_value: string;
  max_drawdown_pct: string;
  is_active: boolean;
  updated_at: string;
}

export interface KillSwitch {
  id: string;
  scope: string;
  scope_ref: string;
  reason: string;
  engaged_by: string;
  engaged_at: string;
  released_at: string | null;
}

export interface RiskEvent {
  id: string;
  account_id: string | null;
  strategy_run_id: string | null;
  event_type: string;
  severity: string;
  message: string;
  details: Record<string, unknown>;
  occurred_at: string;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  tags: string[];
  status: string;
  created_at: string;
  updated_at: string;
  latest_version: number;
  active_runs: number;
}

export interface StrategyVersion {
  id: string;
  strategy_id: string;
  version: number;
  source: string;
  entry_point: string;
  checksum: string;
  manifest: {
    name?: string;
    description?: string;
    parameters?: Array<{
      name: string;
      type: string;
      default: unknown;
      min?: number;
      max?: number;
      description?: string;
    }>;
  };
  approved_for_live: boolean;
  created_at: string;
}

export interface BuiltinManifest {
  name: string;
  entry_point: string;
  description: string;
  required_data: string[];
  parameters: Array<{
    name: string;
    type: string;
    default: unknown;
    min?: number;
    max?: number;
    description?: string;
  }>;
}

export interface StrategyRun {
  id: string;
  strategy_id: string;
  strategy_name: string;
  strategy_version_id: string;
  strategy_version: number;
  account_id: string;
  mode: string;
  state: string;
  parameters: Record<string, unknown>;
  instrument_ids: string[];
  timeframe: string;
  started_at: string | null;
  stopped_at: string | null;
  last_heartbeat_at: string | null;
  error: string | null;
  stats: Record<string, unknown>;
  created_at: string;
}

export interface StrategyLog {
  id: string;
  level: string;
  message: string;
  context: Record<string, unknown>;
  logged_at: string;
}

export interface DashboardSummary {
  total_equity: string;
  total_cash: string;
  starting_balance: string;
  realized_pnl_today: string;
  unrealized_pnl: string;
  open_positions: number;
  open_orders: number;
  active_strategies: number;
  accounts: number;
  trades_today: number;
}

export interface EquityPoint {
  as_of: string;
  equity: string;
  cash: string;
  realized_pnl: string;
  unrealized_pnl: string;
  exposure: string;
}

export interface DailyPnl {
  day: string;
  realized_pnl: string;
  trades: number;
  fees: string;
}

export interface MonthlyPnl {
  month: string;
  realized_pnl: string;
  trades: number;
}

export interface PerformanceSummary {
  total_realized_pnl: string;
  total_unrealized_pnl: string;
  total_fees: string;
  total_trades: number;
  closing_trades: number;
  win_rate_pct: string;
  profit_factor: string | null;
  average_win: string;
  average_loss: string;
  max_drawdown_pct: string;
  daily_return_volatility_pct: string;
  gross_exposure: string;
  sharpe_ratio: string;
  sortino_ratio: string;
  calmar_ratio: string;
  annualized_return_pct: string;
}

export interface Exposure {
  instrument_id: string;
  symbol: string;
  asset_class: string;
  currency: string;
  quantity: string;
  market_value: string;
  side: "long" | "short";
}

export interface AppNotification {
  id: string;
  type: string;
  severity: "info" | "success" | "warning" | "critical";
  title: string;
  body: string;
  payload: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

export interface MobileDevice {
  id: string;
  platform: string;
  app_version: string | null;
  device_name: string | null;
  created_at: string;
  last_seen_at: string;
}

export interface NotificationPreference {
  enabled_channels: string[];
  muted_types: string[];
  min_severity: "info" | "success" | "warning" | "critical";
  quiet_start: string | null;
  quiet_end: string | null;
  critical_overrides_quiet: boolean;
  webhook_url: string | null;
}

export interface AuditEntry {
  id: string;
  actor_user_id: string | null;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id: string;
  request_id: string | null;
  correlation_id: string | null;
  session_id: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  sequence: number | null;
  entry_hash: string | null;
  occurred_at: string;
}

export interface AuditFilters {
  actionPrefix?: string;
  correlationId?: string;
  resourceType?: string;
  occurredFrom?: string;
  occurredTo?: string;
}

export interface MarketplaceListing {
  id: string;
  strategy_id: string;
  title: string;
  summary: string;
  status: string;
  pricing_model: string;
  price: string;
  currency: string;
  revenue_share_percent: string;
  review_count: number;
  average_rating: number;
  license_count: number;
}

export interface MarketplaceLicense {
  id: string;
  listing_id: string;
  kind: string;
  status: string;
  granted_at: string;
  expires_at: string | null;
}

export interface FeatureFlag {
  key: string;
  description: string;
  enabled: boolean;
  kill_switch: boolean;
  rollout_percentage: number;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  status: string;
  email_verified: boolean;
  mfa_enabled: boolean;
  is_platform_admin: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AdminOrganization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  plan_code: string | null;
  subscription_status: string | null;
}

export interface AdminCoupon {
  id: string;
  code: string;
  description: string;
  percent_off: string | null;
  amount_off: string | null;
  currency: string;
  max_redemptions: number | null;
  redeemed_count: number;
  valid_from: string | null;
  valid_until: string | null;
  is_active: boolean;
  applies_plan_codes: string[];
}

export interface SystemHealth {
  database: boolean;
  redis: boolean;
  outbox_backlog: number;
  market_data_age_seconds: number | null;
  engine_heartbeat_age_seconds: number | null;
  active_runs: number;
}
