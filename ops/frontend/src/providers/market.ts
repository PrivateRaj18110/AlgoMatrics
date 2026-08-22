import { createContext, useContext } from 'react'
import type { Market, MarketMeta } from '@/types'

export interface MarketContextValue {
  /** The active market id. */
  market: Market
  /** Static metadata (currency, session, exchanges, symbols…). */
  meta: MarketMeta
  /** Format a value in the active market's currency. */
  money: (value: number, opts?: { precise?: boolean; signed?: boolean }) => string
  /** Compact money for axes / dense cards (`₹12.3L`, `$1.2M`). */
  compactMoney: (value: number) => string
}

export const MarketContext = createContext<MarketContextValue | null>(null)

/** Access the active market. Throws outside a <MarketProvider> (market routes). */
export function useMarket(): MarketContextValue {
  const ctx = useContext(MarketContext)
  if (!ctx) {
    throw new Error('useMarket must be used within a market route (<MarketProvider>)')
  }
  return ctx
}

/** Like {@link useMarket} but returns `null` outside a market route. */
export function useMarketOptional(): MarketContextValue | null {
  return useContext(MarketContext)
}
