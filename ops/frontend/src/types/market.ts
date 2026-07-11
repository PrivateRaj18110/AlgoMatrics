/**
 * Market namespace — the keystone dimension of the platform.
 *
 * Every transactional record (strategy, trade, …) belongs to exactly one
 * market. India and International maintain completely independent data: their
 * own exchanges, brokers, currencies, sessions and symbols. Nothing is shared
 * or mixed across the boundary.
 */

/** The two top-level trading namespaces. */
export type Market = 'india' | 'international'

/** Stable ordering used by the sidebar and any market iteration. */
export const MARKET_IDS: readonly Market[] = ['india', 'international'] as const

/** Static metadata describing how a market trades, prices and displays. */
export interface MarketMeta {
  id: Market
  /** Full label, e.g. `India`. */
  label: string
  /** Compact tag for dense UI, e.g. `IN`, `INTL`. */
  shortLabel: string
  /** ISO 4217 currency code used for every monetary value in this market. */
  currency: string
  /** Display glyph, e.g. `₹`, `$`. */
  currencySymbol: string
  /** BCP 47 locale used for number / date formatting. */
  locale: string
  /** IANA timezone of the primary trading session. */
  timezone: string
  /** Human session window, e.g. `09:15–15:30 IST`. */
  session: string
  /** Exchanges / venues available in this market. */
  exchanges: readonly string[]
  /** Representative tradable symbols. */
  symbols: readonly string[]
}

/** Single source of truth for per-market behaviour. */
export const MARKETS: Record<Market, MarketMeta> = {
  india: {
    id: 'india',
    label: 'India',
    shortLabel: 'IN',
    currency: 'INR',
    currencySymbol: '₹',
    locale: 'en-IN',
    timezone: 'Asia/Kolkata',
    session: '09:15–15:30 IST',
    exchanges: ['NSE', 'BSE', 'MCX', 'NFO', 'CDS'],
    symbols: [
      'NIFTY',
      'BANKNIFTY',
      'FINNIFTY',
      'MIDCPNIFTY',
      'SENSEX',
      'CRUDEOIL',
      'GOLD',
      'SILVER',
    ],
  },
  international: {
    id: 'international',
    label: 'International',
    shortLabel: 'INTL',
    currency: 'USD',
    currencySymbol: '$',
    locale: 'en-US',
    timezone: 'America/New_York',
    session: '24/5 · 09:30–16:00 ET',
    exchanges: ['Forex', 'CME', 'NASDAQ', 'NYSE', 'Crypto'],
    symbols: [
      'EURUSD',
      'GBPUSD',
      'USDJPY',
      'GBPJPY',
      'XAUUSD',
      'XAGUSD',
      'NAS100',
      'US30',
      'SP500',
      'BTCUSD',
      'ETHUSD',
    ],
  },
}

/** Type guard: is an arbitrary string one of the known market ids? */
export function isMarket(value: string | undefined): value is Market {
  return value === 'india' || value === 'international'
}

/** Resolve a market's metadata. Falls back to India for unknown input. */
export function getMarketMeta(market: Market): MarketMeta {
  return MARKETS[market]
}
