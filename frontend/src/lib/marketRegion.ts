/** Classify real telemetry into India vs International. Never invent symbols. */

export type MarketRegion = "india" | "international";

const INDIA_SYMBOLS = new Set(
  [
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "SENSEX",
    "NIFTYNXT",
    "CRUDEOIL",
    "NATURALGAS",
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
    "XAUUSD",
    "XAGUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "GBPJPY",
    "BTCUSD",
    "ETHUSD",
    "BTCUSDT",
    "ETHUSDT",
  ].map((value) => value.toUpperCase()),
);

const INDIA_BROKERS = new Set(["zerodha", "angelone", "flattrade", "delta"]);
const INTERNATIONAL_BROKERS = new Set(["mt5", "binance", "interactive_brokers"]);

const INDIA_LOCATION = /india|mumbai|bengaluru|bangalore|hyderabad|nse|bse|kolkata|delhi/i;
const INTERNATIONAL_LOCATION = /new york|virginia|london|frankfurt|tokyo|forex|nasdaq|nyse|gcp/i;

function token(value: string | null | undefined): string {
  return (value ?? "").trim().toUpperCase();
}

export function classifySymbol(symbol: string | null | undefined): MarketRegion | null {
  const raw = (symbol ?? "").trim();
  if (!raw) return null;
  const upper = raw.toUpperCase();
  if (upper.endsWith(".NS") || upper.endsWith(".BO") || upper.endsWith(":NSE") || upper.endsWith(":BSE")) {
    return "india";
  }
  const head = upper.split(/[\s-]+/)[0] ?? upper;
  if (INDIA_SYMBOLS.has(head) || INDIA_SYMBOLS.has(upper)) return "india";
  if (INTERNATIONAL_SYMBOLS.has(head) || INTERNATIONAL_SYMBOLS.has(upper)) return "international";
  if (/^[A-Z]{6}$/.test(head) && /USD|EUR|GBP|JPY|AUD|CAD|CHF/.test(head)) return "international";
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
}): MarketRegion | null {
  return (
    classifySymbol(row.symbol) ??
    classifyBroker(row.broker_code) ??
    classifyLocation(row.location) ??
    classifyLocation(row.hostname) ??
    classifyLocation(row.machine) ??
    classifyLocation(row.name)
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
