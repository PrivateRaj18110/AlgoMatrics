import type { Market, Trade, TradeDirection, TradeStatus } from '@/types'
import { MARKET_IDS } from '@/types'
import { MOCK_STRATEGIES } from './strategies.mock'
import { createRng, MARKET_REFERENCE, pick, randFloat, randInt, round } from './seed'

const rng = createRng(0x7ade5)

/** Trades generated per market — keeps each blotter sized realistically. */
const TRADES_PER_MARKET = 96

function buildTrade(market: Market, seq: number): Trade {
  const ref = MARKET_REFERENCE[market]
  const marketStrategies = MOCK_STRATEGIES.filter((s) => s.market === market)
  const strat = pick(rng, marketStrategies)
  const symbol = pick(rng, strat.symbols.length ? strat.symbols : ref.symbols)
  const direction: TradeDirection = rng() > 0.5 ? 'long' : 'short'
  const base = ref.basePrice[symbol] ?? 100
  const precision = base > 1000 ? 1 : 4
  const entry = round(base * randFloat(rng, 0.995, 1.005), precision)

  // Closed trades dominate; a handful remain open.
  const isOpen = rng() < 0.12
  const status: TradeStatus = isOpen ? 'open' : rng() < 0.04 ? 'cancelled' : 'closed'

  const moveR = randFloat(rng, -1.4, 1.7) // skew slightly positive
  const exit =
    status === 'closed'
      ? round(entry * (1 + (direction === 'long' ? moveR : -moveR) * 0.004), precision)
      : null

  const quantity = round(randFloat(rng, 0.2, 5), 2)
  // Directional pnl: a long profits on a positive move, a short on a negative one.
  const directionalMove = direction === 'long' ? moveR : -moveR
  const pnl =
    status === 'cancelled'
      ? 0
      : round(directionalMove * quantity * randFloat(rng, 60, 240) * ref.pnlScale, 0)

  const minutesAgo = randInt(rng, 1, 60 * 96) // up to ~4 days back
  const label = market === 'india' ? 'in' : 'intl'
  return {
    id: `trd-${label}-${(TRADES_PER_MARKET - seq).toString().padStart(4, '0')}`,
    market,
    time: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
    strategy: strat.name,
    machine: strat.machineName,
    broker: pick(rng, ref.brokers),
    account: pick(rng, ref.accounts),
    symbol,
    direction,
    entry,
    exit,
    quantity,
    pnl,
    latencyMs: round(randFloat(rng, 14, 280), 0),
    durationSec: status === 'open' ? randInt(rng, 60, 7200) : randInt(rng, 20, 14_400),
    status,
  }
}

/** All trades across every market — filter by `market` at the service layer. */
export const MOCK_TRADES: Trade[] = MARKET_IDS.flatMap((market) =>
  Array.from({ length: TRADES_PER_MARKET }, (_, i) => buildTrade(market, i)),
).sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
