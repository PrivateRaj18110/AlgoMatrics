import type { LogEntry, LogLevel, LogSource } from '@/types'
import { createRng, pick, randInt } from './seed'

const rng = createRng(0x106a)

interface Template {
  source: LogSource
  level: LogLevel
  logger: string
  message: string
}

/** A representative line per stream / level so every filter shows content. */
const TEMPLATES: Template[] = [
  { source: 'application', level: 'info', logger: 'api.gateway', message: 'GET /api/dashboard/overview 200 in 18ms' },
  { source: 'application', level: 'info', logger: 'ws.broadcast', message: 'Pushed overview snapshot to 3 clients' },
  { source: 'application', level: 'warn', logger: 'api.ratelimit', message: 'Client 10.0.0.4 approaching rate limit (88/100)' },
  { source: 'strategy', level: 'info', logger: 'MR-FX', message: 'Signal generated: SELL EURUSD size=1.2' },
  { source: 'strategy', level: 'info', logger: 'MOM', message: 'Position opened LONG NAS100 @ 18642.5' },
  { source: 'strategy', level: 'warn', logger: 'GRID', message: 'Grid level 7 reached — pausing new entries' },
  { source: 'strategy', level: 'error', logger: 'GRID', message: 'Strategy exited unexpectedly with code 1' },
  { source: 'python', level: 'debug', logger: 'monitor_sdk', message: 'heartbeat() flushed 1 metric batch' },
  { source: 'python', level: 'info', logger: 'runtime', message: 'Python 3.12.4 runtime started, pid=20488' },
  { source: 'python', level: 'error', logger: 'asyncio', message: 'Task exception: ConnectionResetError(10054)' },
  { source: 'broker', level: 'info', logger: 'mt5.bridge', message: 'MT5 terminal connected — ICMarkets-Live12' },
  { source: 'broker', level: 'warn', logger: 'mt5.bridge', message: 'Requote on order #88213, retrying' },
  { source: 'broker', level: 'error', logger: 'fix.session', message: 'FIX session dropped, reconnecting in 3s' },
  { source: 'database', level: 'info', logger: 'supabase.pool', message: 'Connection pool established (size=10)' },
  { source: 'database', level: 'debug', logger: 'supabase.query', message: 'INSERT trades (id, pnl) committed in 4ms' },
  { source: 'system', level: 'info', logger: 'host.london', message: 'CPU 41% · RAM 62% · disk 47%' },
  { source: 'system', level: 'warn', logger: 'host.gcloud', message: 'CPU sustained >85% for 6m' },
  { source: 'system', level: 'error', logger: 'host.pc', message: 'Heartbeat timeout — host marked offline' },
]

export const MOCK_LOGS: LogEntry[] = Array.from({ length: 220 }, (_, i) => {
  const tpl = pick(rng, TEMPLATES)
  return {
    id: `log-${(2200 - i).toString().padStart(5, '0')}`,
    time: new Date(Date.now() - i * randInt(rng, 2, 18) * 1000).toISOString(),
    source: tpl.source,
    level: tpl.level,
    logger: tpl.logger,
    message: tpl.message,
  }
}).sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
