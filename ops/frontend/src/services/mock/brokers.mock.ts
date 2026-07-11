import type { Broker, Status, TimeSeriesPoint } from '@/types'
import { createRng, randFloat, randInt, round } from './seed'

const rng = createRng(0xb20c)

/** Recent ping history for a broker card sparkline. */
function pingHistory(base: number, points = 24): TimeSeriesPoint[] {
  return Array.from({ length: points }, (_, i) => ({
    t: `${i}`,
    v: round(Math.max(1, base + randFloat(rng, -base * 0.4, base * 0.6)), 1),
  }))
}

interface Blueprint {
  id: string
  name: string
  server: string
  account: string
  connection: Status
  leverage: number
  basePing: number
  baseSpread: number
}

const BLUEPRINTS: Blueprint[] = [
  { id: 'brk-icm', name: 'IC Markets', server: 'ICMarkets-Live12', account: 'LIVE-001', connection: 'online', leverage: 500, basePing: 4, baseSpread: 0.1 },
  { id: 'brk-pep', name: 'Pepperstone', server: 'Pepperstone-Live04', account: 'LIVE-002', connection: 'online', leverage: 400, basePing: 7, baseSpread: 0.2 },
  { id: 'brk-ib', name: 'Interactive Brokers', server: 'IBKR-Gateway-LD4', account: 'LIVE-003', connection: 'degraded', leverage: 50, basePing: 38, baseSpread: 0.4 },
  { id: 'brk-bin', name: 'Binance', server: 'Binance-Spot-FIX', account: 'PROP-114', connection: 'online', leverage: 20, basePing: 22, baseSpread: 0.5 },
]

export const MOCK_BROKERS: Broker[] = BLUEPRINTS.map((bp) => {
  const offline = bp.connection === 'offline'
  const balance = round(randFloat(rng, 40_000, 260_000), 0)
  const openPnl = offline ? 0 : round(randFloat(rng, -4_200, 8_400), 0)
  const equity = round(balance + openPnl, 0)
  const margin = offline ? 0 : round(randFloat(rng, 2_000, 28_000), 0)
  const freeMargin = round(equity - margin, 0)
  const pingMs = offline ? 0 : round(bp.basePing + randFloat(rng, 0, bp.basePing), 0)
  return {
    id: bp.id,
    name: bp.name,
    server: bp.server,
    connection: bp.connection,
    account: bp.account,
    spreadPips: round(bp.baseSpread + randFloat(rng, 0, 0.6), 2),
    balance,
    equity,
    margin,
    freeMargin,
    marginLevelPct: margin > 0 ? round((equity / margin) * 100, 0) : 0,
    leverage: bp.leverage,
    openPositions: offline ? 0 : randInt(rng, 0, 9),
    pendingOrders: offline ? 0 : randInt(rng, 0, 5),
    rejectedOrders: randInt(rng, 0, 4),
    pingMs,
    lastSync: new Date(Date.now() - randInt(rng, 1, offline ? 600 : 12) * 1000).toISOString(),
    pingHistory: pingHistory(Math.max(bp.basePing, 3)),
  }
})
