export type MarketRegion = "india" | "international";

/**
 * Single source of truth for market availability in the UI.
 * Set to `true` to re-enable the International market selector and routes.
 */
export const INTERNATIONAL_MARKET_ENABLED = false;

export const VISIBLE_MARKETS: readonly MarketRegion[] = INTERNATIONAL_MARKET_ENABLED
  ? (["india", "international"] as const)
  : (["india"] as const);

const INDIA_INDEX_PREFIX =
  /^(NIFTY|BANKNIFTY|FINNIFTY|MIDCPNIFTY|SENSEX|BANKEX|NIFTYNXT|CRUDEOIL|NATURALGAS|GOLDM|SILVERM)/i;

const INDIA_SYMBOLS = new Set(
  [
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "SENSEX",
    "BANKEX",
    "NIFTYNXT",
    "NIFTYNXT50",
    "CRUDEOIL",
    "NATURALGAS",
    "GOLDM",
    "SILVERM",
  ].map((value) => value.toUpperCase()),
);

const INTERNATIONAL_SYMBOLS = new Set(
  [
    "USTEC",
    "NAS100",
    "US100",
    "US30",
    "SPX",
    "SP500",
    "NDX",
    "DJI",
    "DAX",
    "FTSE",
    "XAUUSD",
    "XAGUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "GBPJPY",
    "EURGBP",
    "EURJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "NZDUSD",
    "BTCUSD",
    "ETHUSD",
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
  ].map((value) => value.toUpperCase()),
);

const INDIA_BROKERS = new Set([
  "zerodha",
  "angelone",
  "flattrade",
  "delta",
  "dhan",
  "fyers",
  "shoonya",
  "finvasia",
  "kotak",
  "icici",
  "upstox",
  "groww",
  "aliceblue",
  "iifl",
]);

const INTERNATIONAL_BROKERS = new Set([
  "mt4",
  "mt5",
  "binance",
  "interactive_brokers",
  "ibkr",
  "oanda",
  "bybit",
  "coinbase",
]);

const INDIA_LOCATION =
  /india|mumbai|bengaluru|bangalore|hyderabad|nse|bse|kolkata|delhi|chennai|asia-south/i;
const INTERNATIONAL_LOCATION =
  /new york|virginia|london|frankfurt|tokyo|forex|nasdaq|nyse|equinix ld4|equinix ny4/i;

function token(value: string | null | undefined): string {
  return (value ?? "").trim().toUpperCase();
}

export function classifySymbol(symbol: string | null | undefined): MarketRegion | null {
  const raw = (symbol ?? "").trim();
  if (!raw) return null;
  const upper = raw.toUpperCase();

  // Explicit exchange suffix
  if (
    upper.endsWith(".NS") ||
    upper.endsWith(".BO") ||
    upper.endsWith(":NSE") ||
    upper.endsWith(":BSE") ||
    upper.endsWith("-EQ") ||
    upper.endsWith("-BE")
  ) {
    return "india";
  }

  // Explicit international catalog or forex / crypto
  const head = upper.split(/[\s-]+/)[0] ?? upper;
  if (INTERNATIONAL_SYMBOLS.has(head) || INTERNATIONAL_SYMBOLS.has(upper)) {
    return "international";
  }
  if (/^[A-Z]{6}$/.test(head) && /USD|EUR|GBP|JPY|AUD|CAD|CHF/.test(head)) {
    return "international";
  }
  if (upper.endsWith("USDT") || upper.endsWith("BUSD") || upper.endsWith("USDC")) {
    return "international";
  }

  // Indian index or derivative contracts
  if (INDIA_SYMBOLS.has(head) || INDIA_SYMBOLS.has(upper) || INDIA_INDEX_PREFIX.test(head)) {
    return "india";
  }

  // Option derivative notation (CE / PE / FUT)
  if (/\b(CE|PE|FUT)\b/i.test(upper) || /\d{4,6}\s*(?:CE|PE)\b/i.test(upper)) {
    return "india";
  }

  // Standard alphanumeric equity ticker (e.g. RELIANCE, TCS, INFY)
  if (/^[A-Z0-9&_]+$/.test(head)) {
    return "india";
  }

  return null;
}

export function classifyBroker(code: string | null | undefined): MarketRegion | null {
  const value = (code ?? "").trim().toLowerCase();
  if (INDIA_BROKERS.has(value)) return "india";
  if (INTERNATIONAL_BROKERS.has(value)) return "international";
  return null;
}

export function classifyLocation(location: string | null | undefined): MarketRegion | null {
  const value = location ?? "";
  if (!value.trim()) return null;
  if (INDIA_LOCATION.test(value)) return "india";
  if (INTERNATIONAL_LOCATION.test(value)) return "international";
  return null;
}

export function classifyRow(row: {
  symbol?: string | null;
  machine?: string | null;
  location?: string | null;
  hostname?: string | null;
  name?: string | null;
  broker_code?: string | null;
  broker?: string | null;
  strategy?: string | null;
  strategy_name?: string | null;
}): MarketRegion | null {
  return (
    classifySymbol(row.symbol) ??
    classifyBroker(row.broker_code ?? row.broker) ??
    classifyLocation(row.location) ??
    classifyLocation(row.hostname) ??
    classifyLocation(row.machine) ??
    classifyLocation(row.name) ??
    "india"
  );
}

export function inRegion<T extends Parameters<typeof classifyRow>[0]>(
  region: MarketRegion,
  rows: T[] | undefined | null,
): T[] {
  return (rows ?? []).filter((row) => classifyRow(row) === region);
}

export function regionEmptyCopy(region: MarketRegion): string {
  return region === "india" ? "No India data available." : "No international data available.";
}

export function regionLabel(region: MarketRegion): string {
  return region === "india" ? "India" : "International";
}

export function regionZone(region: MarketRegion): "Asia/Kolkata" | "America/New_York" {
  return region === "india" ? "Asia/Kolkata" : "America/New_York";
}

export { token };

