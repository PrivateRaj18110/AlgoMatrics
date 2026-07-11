import type { EventCategory, Severity, SystemEvent } from '@/types'
import { createRng, pick, randInt, round, SYMBOLS } from './seed'

const rng = createRng(0xe7e7)

interface Template {
  category: EventCategory
  severity: Severity
  build: () => { source: string; message: string }
}

const MACHINES = ['London VPS', 'Google Cloud', 'Personal Computer']
const STRATS = ['MR-FX', 'MOM', 'XAU-SC', 'CT', 'NF', 'GRID']
const BROKERS = ['IC Markets', 'Pepperstone', 'Interactive Brokers', 'Binance']

/** Event templates mirror the live event terminal examples in the spec. */
const TEMPLATES: Template[] = [
  {
    category: 'trade',
    severity: 'info',
    build: () => {
      const sym = pick(rng, SYMBOLS)
      const dir = rng() > 0.5 ? 'LONG' : 'SHORT'
      return { source: pick(rng, STRATS), message: `Trade opened ${dir} ${sym} @ ${round(1 + rng(), 4)}` }
    },
  },
  {
    category: 'trade',
    severity: 'info',
    build: () => {
      const sym = pick(rng, SYMBOLS)
      const pnl = round((rng() - 0.4) * 1800, 0)
      return { source: pick(rng, STRATS), message: `Trade closed ${sym} · PnL ${pnl >= 0 ? '+' : ''}$${pnl}` }
    },
  },
  { category: 'strategy', severity: 'info', build: () => ({ source: pick(rng, STRATS), message: 'Strategy started' }) },
  { category: 'strategy', severity: 'warning', build: () => ({ source: pick(rng, STRATS), message: 'Strategy stopped by operator' }) },
  { category: 'machine', severity: 'warning', build: () => ({ source: pick(rng, MACHINES), message: `High CPU load ${randInt(rng, 86, 98)}%` }) },
  { category: 'machine', severity: 'critical', build: () => ({ source: pick(rng, MACHINES), message: 'Machine offline — heartbeat lost' }) },
  { category: 'machine', severity: 'critical', build: () => ({ source: pick(rng, MACHINES), message: 'Internet connection lost' }) },
  { category: 'broker', severity: 'info', build: () => ({ source: pick(rng, BROKERS), message: 'Broker connected' }) },
  { category: 'broker', severity: 'warning', build: () => ({ source: pick(rng, BROKERS), message: `Elevated latency ${randInt(rng, 180, 420)}ms` }) },
  { category: 'database', severity: 'info', build: () => ({ source: 'Supabase', message: 'Database connected' }) },
  { category: 'system', severity: 'critical', build: () => ({ source: pick(rng, STRATS), message: 'Python exception: ConnectionResetError' }) },
  { category: 'risk', severity: 'warning', build: () => ({ source: 'Risk Engine', message: `Exposure ${randInt(rng, 60, 92)}% of daily cap` }) },
]

/** Build one event positioned `secondsAgo` in the past. */
export function buildEvent(secondsAgo: number, id: string): SystemEvent {
  const tpl = pick(rng, TEMPLATES)
  const { source, message } = tpl.build()
  return {
    id,
    time: new Date(Date.now() - secondsAgo * 1000).toISOString(),
    category: tpl.category,
    severity: tpl.severity,
    source,
    message,
  }
}

export const MOCK_EVENTS: SystemEvent[] = Array.from({ length: 80 }, (_, i) =>
  buildEvent(i * randInt(rng, 8, 40), `evt-${(800 - i).toString().padStart(4, '0')}`),
).sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
