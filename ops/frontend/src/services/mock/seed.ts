/**
 * Deterministic helpers for the mock data layer.
 *
 * A seeded PRNG keeps generated data stable across renders / service calls so
 * charts and grids don't jump every time a component re-mounts. All mock data
 * modules build their fixtures once at import time using these helpers.
 */

/** mulberry32 — tiny, fast, deterministic PRNG. */
export function createRng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Random float in `[min, max)`. */
export function randFloat(rng: () => number, min: number, max: number): number {
  return min + rng() * (max - min)
}

/** Random integer in `[min, max]`. */
export function randInt(rng: () => number, min: number, max: number): number {
  return Math.floor(randFloat(rng, min, max + 1))
}

/** Pick a random element from an array. */
export function pick<T>(rng: () => number, arr: readonly T[]): T {
  return arr[Math.floor(rng() * arr.length)]
}

/** Round to N decimals. */
export function round(value: number, decimals = 2): number {
  const f = 10 ** decimals
  return Math.round(value * f) / f
}

/** Reference data shared by the fixtures (International market). */
export const SYMBOLS = [
  'EURUSD',
  'GBPUSD',
  'USDJPY',
  'XAUUSD',
  'BTCUSD',
  'ETHUSD',
  'NAS100',
  'SPX500',
  'US30',
  'AUDUSD',
] as const

export const BROKERS = ['IC Markets', 'Pepperstone', 'Interactive Brokers', 'Binance'] as const

export const ACCOUNTS = ['LIVE-001', 'LIVE-002', 'LIVE-003', 'PROP-114'] as const

/* ----------------------------------------------------------------------------
 * Per-market reference data.
 *
 * India and International draw from entirely separate pools of symbols,
 * brokers, machines and accounts so the two namespaces never share an
 * identifier. Prices are quoted in each market's native currency.
 * ------------------------------------------------------------------------- */

import type { Market } from '@/types'

export interface MarketReference {
  /** Tradable symbols for this market. */
  symbols: readonly string[]
  /** Brokers operating in this market. */
  brokers: readonly string[]
  /** Trading accounts in this market's currency. */
  accounts: readonly string[]
  /** Hosts (id + display name) running this market's strategies. */
  machines: readonly { id: string; name: string }[]
  /** Reference price per symbol, in the market's native currency. */
  basePrice: Record<string, number>
  /**
   * Rough scale of a single strategy's daily PnL swing in native currency.
   * INR magnitudes are ~80x USD, so India numbers read in lakhs.
   */
  pnlScale: number
}

export const MARKET_REFERENCE: Record<Market, MarketReference> = {
  india: {
    symbols: ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'CRUDEOIL', 'GOLD', 'SILVER'],
    brokers: ['Zerodha', 'Angel One', 'Upstox', 'ICICI Direct', '5paisa'],
    accounts: ['IN-LIVE-01', 'IN-LIVE-02', 'IN-PROP-07', 'IN-HFT-11'],
    machines: [
      { id: 'mch-mumbai-colo', name: 'Mumbai Colo (NSE)' },
      { id: 'mch-mumbai-vps', name: 'Mumbai VPS' },
      { id: 'mch-delhi-pc', name: 'Delhi Desk' },
    ],
    basePrice: {
      NIFTY: 23_550,
      BANKNIFTY: 51_240,
      FINNIFTY: 23_180,
      MIDCPNIFTY: 12_420,
      SENSEX: 77_320,
      CRUDEOIL: 6_480,
      GOLD: 71_650,
      SILVER: 89_400,
    },
    pnlScale: 80,
  },
  international: {
    symbols: SYMBOLS,
    brokers: BROKERS,
    accounts: ACCOUNTS,
    machines: [
      { id: 'mch-london', name: 'London VPS' },
      { id: 'mch-gcloud', name: 'Google Cloud' },
      { id: 'mch-ny4', name: 'NY4 Equinix' },
    ],
    basePrice: {
      EURUSD: 1.085,
      GBPUSD: 1.272,
      USDJPY: 156.4,
      GBPJPY: 198.9,
      XAUUSD: 2348,
      XAGUSD: 30.4,
      BTCUSD: 64_210,
      ETHUSD: 3420,
      NAS100: 18_650,
      SP500: 5430,
      SPX500: 5430,
      US30: 39_120,
      AUDUSD: 0.662,
    },
    pnlScale: 1,
  },
}
