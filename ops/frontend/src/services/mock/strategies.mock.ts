import type { Market, Status, Strategy, TimeSeriesPoint } from '@/types'
import { MARKET_IDS } from '@/types'
import { createRng, MARKET_REFERENCE, pick, randFloat, randInt, round } from './seed'

const rng = createRng(0xa17a)

/** Build an intraday sparkline of cumulative pnl. */
function buildSparkline(base: number, points = 24): TimeSeriesPoint[] {
  let acc = 0
  const out: TimeSeriesPoint[] = []
  for (let i = 0; i < points; i++) {
    acc += randFloat(rng, -1, 1.15) * base
    out.push({ t: `${i}:00`, v: round(acc, 1) })
  }
  return out
}

interface Blueprint {
  name: string
  code: string
  description: string
  /** Index into the market's machine pool. */
  machine: number
  status: Status
}

/** Independent strategy rosters — one blueprint set per market. */
const BLUEPRINTS: Record<Market, Blueprint[]> = {
  india: [
    {
      name: 'NIFTY Options Scalper',
      code: 'NF-SC',
      description: 'High-frequency scalping on weekly NIFTY options.',
      machine: 0,
      status: 'online',
    },
    {
      name: 'BankNifty Momentum',
      code: 'BN-MOM',
      description: 'Intraday momentum bursts on BANKNIFTY futures.',
      machine: 0,
      status: 'online',
    },
    {
      name: 'Index Straddle',
      code: 'IDX-STR',
      description: 'Expiry-day short straddle with delta hedging.',
      machine: 0,
      status: 'online',
    },
    {
      name: 'FinNifty Expiry',
      code: 'FN-EXP',
      description: 'Theta harvesting around FINNIFTY expiry.',
      machine: 1,
      status: 'degraded',
    },
    {
      name: 'MCX Gold Trend',
      code: 'GLD-TR',
      description: 'Trend following on MCX GOLD / SILVER.',
      machine: 1,
      status: 'online',
    },
    {
      name: 'Crude Reversal',
      code: 'CR-REV',
      description: 'Mean reversion on MCX CRUDEOIL.',
      machine: 1,
      status: 'online',
    },
    {
      name: 'Midcap Breakout',
      code: 'MC-BO',
      description: 'Breakout capture on MIDCPNIFTY.',
      machine: 2,
      status: 'offline',
    },
  ],
  international: [
    {
      name: 'Mean Reversion FX',
      code: 'MR-FX',
      description: 'Intraday mean reversion across major FX pairs.',
      machine: 0,
      status: 'online',
    },
    {
      name: 'Momentum Breakout',
      code: 'MOM',
      description: 'Volatility-adjusted breakout on indices.',
      machine: 0,
      status: 'online',
    },
    {
      name: 'Gold Scalper',
      code: 'XAU-SC',
      description: 'High-frequency scalping on XAUUSD.',
      machine: 0,
      status: 'online',
    },
    {
      name: 'Stat Arb Pairs',
      code: 'ARB',
      description: 'Cointegration-based statistical arbitrage.',
      machine: 0,
      status: 'degraded',
    },
    {
      name: 'Crypto Trend',
      code: 'CT',
      description: 'Multi-timeframe trend following on BTC/ETH.',
      machine: 1,
      status: 'online',
    },
    {
      name: 'Index Overnight',
      code: 'IDX-ON',
      description: 'Overnight drift capture on US indices.',
      machine: 1,
      status: 'online',
    },
    {
      name: 'News Fade',
      code: 'NF',
      description: 'Fades post-news overreactions on FX.',
      machine: 1,
      status: 'degraded',
    },
    {
      name: 'Grid Hedge',
      code: 'GRID',
      description: 'Hedged grid on ranging majors.',
      machine: 2,
      status: 'offline',
    },
  ],
}

function buildMarketStrategies(market: Market): Strategy[] {
  const ref = MARKET_REFERENCE[market]
  return BLUEPRINTS[market].map((bp, i) => {
    const offline = bp.status === 'offline'
    const machine = ref.machines[bp.machine] ?? ref.machines[0]
    const todayPnl = offline ? 0 : round(randFloat(rng, -1800, 4200) * ref.pnlScale, 0)
    return {
      id: `str-${market === 'india' ? 'in' : 'intl'}-${i + 1}`,
      market,
      name: bp.name,
      code: bp.code,
      description: bp.description,
      status: bp.status,
      machineId: machine.id,
      machineName: machine.name,
      broker: pick(rng, ref.brokers),
      // Dedupe — a strategy should never list the same symbol twice.
      symbols: Array.from(
        new Set(Array.from({ length: randInt(rng, 1, 3) }, () => pick(rng, ref.symbols))),
      ),
      todayPnl,
      weekPnl: offline
        ? round(randFloat(rng, -2000, 1000) * ref.pnlScale, 0)
        : round(todayPnl + randFloat(rng, -3000, 9000) * ref.pnlScale, 0),
      todayTrades: offline ? 0 : randInt(rng, 4, 64),
      openPositions: offline ? 0 : randInt(rng, 0, 6),
      winRate: round(randFloat(rng, 41, 71), 1),
      profitFactor: round(randFloat(rng, 0.9, 2.6), 2),
      avgLatencyMs: round(randFloat(rng, 18, 240), 0),
      sparkline: buildSparkline(randFloat(rng, 60, 220) * ref.pnlScale),
      lastHeartbeat: new Date(Date.now() - randInt(rng, 2, offline ? 600 : 30) * 1000).toISOString(),
    }
  })
}

/** All strategies across every market — filter by `market` at the service layer. */
export const MOCK_STRATEGIES: Strategy[] = MARKET_IDS.flatMap((m) => buildMarketStrategies(m))
