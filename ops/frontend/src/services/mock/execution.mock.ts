import type {
  ExecutionData,
  ExecutionFlowSample,
  ExecutionResult,
  ExecutionStage,
  LatencyBucket,
  TimeSeriesPoint,
} from '@/types'
import { MOCK_STRATEGIES } from './strategies.mock'
import { createRng, pick, randFloat, randInt, round, SYMBOLS } from './seed'

const rng = createRng(0xe7ec)

/**
 * Pipeline funnel. `count` tapers as orders drop out at the risk gate and the
 * broker (rejections), so the stages tell a realistic story.
 */
const signalCount = 1284
const stages: ExecutionStage[] = (() => {
  const defs: Array<{ key: ExecutionStage['key']; label: string; avgMs: number }> = [
    { key: 'signal', label: 'Signal Generated', avgMs: 0 },
    { key: 'risk', label: 'Risk Passed', avgMs: 2 },
    { key: 'created', label: 'Order Created', avgMs: 1 },
    { key: 'sent', label: 'Order Sent', avgMs: 3 },
    { key: 'received', label: 'Broker Received', avgMs: 18 },
    { key: 'filled', label: 'Broker Filled', avgMs: 24 },
    { key: 'open', label: 'Trade Open', avgMs: 1 },
    { key: 'closed', label: 'Trade Closed', avgMs: 0 },
  ]
  let count = signalCount
  return defs.map((d, i) => {
    const prev = count
    // Drop a few orders at the risk gate and at the broker.
    const dropRate = d.key === 'risk' ? 0.06 : d.key === 'filled' ? 0.018 : 0
    count = i === 0 ? count : Math.round(prev * (1 - dropRate))
    const dropped = i === 0 ? 0 : prev - count
    const status: ExecutionStage['status'] =
      d.avgMs >= 40 ? 'warn' : d.avgMs >= 80 ? 'fail' : 'ok'
    return { key: d.key, label: d.label, avgMs: d.avgMs, count, dropped, status }
  })
})()

/** Latency percentiles per leg of the journey. */
const latency: LatencyBucket[] = [
  { label: 'Signal Delay', p50: 2, p90: 5, p95: 8, p99: 16 },
  { label: 'Execution Delay', p50: 4, p90: 9, p95: 14, p99: 27 },
  { label: 'Broker Delay', p50: 18, p90: 41, p95: 58, p99: 96 },
  { label: 'Fill Delay', p50: 24, p90: 52, p95: 73, p99: 132 },
  { label: 'Total Delay', p50: 48, p90: 104, p95: 148, p99: 268 },
]

function buildSample(i: number): ExecutionFlowSample {
  const strat = pick(rng, MOCK_STRATEGIES)
  const signalMs = round(randFloat(rng, 1, 6), 0)
  const riskMs = round(randFloat(rng, 1, 5), 0)
  const execMs = round(randFloat(rng, 2, 12), 0)
  const brokerMs = round(randFloat(rng, 8, 70), 0)
  const fillMs = round(randFloat(rng, 10, 90), 0)
  const roll = rng()
  const result: ExecutionResult = roll < 0.9 ? 'filled' : roll < 0.96 ? 'partial' : 'rejected'
  return {
    id: `exe-${(200 - i).toString().padStart(4, '0')}`,
    time: new Date(Date.now() - i * randInt(rng, 4, 40) * 1000).toISOString(),
    symbol: pick(rng, strat.symbols.length ? strat.symbols : SYMBOLS),
    strategy: strat.code,
    signalMs,
    riskMs,
    execMs,
    brokerMs,
    fillMs,
    totalMs: signalMs + riskMs + execMs + brokerMs + fillMs,
    result,
  }
}

const recent: ExecutionFlowSample[] = Array.from({ length: 60 }, (_, i) => buildSample(i))

/** Orders processed per minute over the last hour. */
const throughput: TimeSeriesPoint[] = Array.from({ length: 60 }, (_, i) => ({
  t: `${i}`,
  v: randInt(rng, 4, 38),
}))

export const MOCK_EXECUTION: ExecutionData = { stages, latency, recent, throughput }
