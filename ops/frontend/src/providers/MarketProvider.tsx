import { useMemo, type ReactNode } from 'react'
import { MARKETS, type Market } from '@/types'
import { formatCompactMoney, formatMoney } from '@/utils/format'
import { MarketContext, type MarketContextValue } from './market'

interface MarketProviderProps {
  market: Market
  children: ReactNode
}

/** Supplies the active market + currency-bound formatters to a route subtree. */
export function MarketProvider({ market, children }: MarketProviderProps) {
  const value = useMemo<MarketContextValue>(
    () => ({
      market,
      meta: MARKETS[market],
      money: (v, opts) => formatMoney(v, market, opts),
      compactMoney: (v) => formatCompactMoney(v, market),
    }),
    [market],
  )

  return <MarketContext.Provider value={value}>{children}</MarketContext.Provider>
}
