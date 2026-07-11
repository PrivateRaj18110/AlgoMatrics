import type { Account, AccountType, Status, TimeSeriesPoint } from '@/types'
import { MOCK_STRATEGIES } from './strategies.mock'
import { createRng, randFloat, randInt, round } from './seed'

const rng = createRng(0xacc7)

function equityCurve(start: number, points = 40): TimeSeriesPoint[] {
  let equity = start
  return Array.from({ length: points }, (_, i) => {
    equity = Math.max(equity * (1 + randFloat(rng, -0.012, 0.016)), start * 0.7)
    return { t: `${i}`, v: round(equity, 0) }
  })
}

interface Blueprint {
  id: string
  label: string
  broker: string
  type: AccountType
  currency: string
  status: Status
  leverage: number
}

const BLUEPRINTS: Blueprint[] = [
  { id: 'acc-live-001', label: 'LIVE-001', broker: 'IC Markets', type: 'live', currency: 'USD', status: 'online', leverage: 500 },
  { id: 'acc-live-002', label: 'LIVE-002', broker: 'Pepperstone', type: 'live', currency: 'USD', status: 'online', leverage: 400 },
  { id: 'acc-live-003', label: 'LIVE-003', broker: 'Interactive Brokers', type: 'live', currency: 'GBP', status: 'degraded', leverage: 50 },
  { id: 'acc-prop-114', label: 'PROP-114', broker: 'Binance', type: 'prop', currency: 'USD', status: 'online', leverage: 20 },
  { id: 'acc-demo-001', label: 'DEMO-001', broker: 'IC Markets', type: 'demo', currency: 'USD', status: 'online', leverage: 500 },
]

const codes = MOCK_STRATEGIES.map((s) => s.code)

export const MOCK_ACCOUNTS: Account[] = BLUEPRINTS.map((bp) => {
  const balance = round(randFloat(rng, 25_000, 320_000), 0)
  const openPnl = bp.status === 'offline' ? 0 : round(randFloat(rng, -3_600, 7_200), 0)
  const todayPnl = bp.status === 'offline' ? 0 : round(randFloat(rng, -2_400, 5_800), 0)
  const equity = round(balance + openPnl, 0)
  return {
    id: bp.id,
    label: bp.label,
    broker: bp.broker,
    type: bp.type,
    currency: bp.currency,
    status: bp.status,
    balance,
    equity,
    todayPnl,
    openPnl,
    marginLevelPct: round(randFloat(rng, 180, 2400), 0),
    leverage: bp.leverage,
    openPositions: bp.status === 'offline' ? 0 : randInt(rng, 0, 8),
    strategies: Array.from(
      new Set(Array.from({ length: randInt(rng, 1, 3) }, () => codes[randInt(rng, 0, codes.length - 1)])),
    ),
    equityCurve: equityCurve(balance * randFloat(rng, 0.85, 0.95)),
  }
})
