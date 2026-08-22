import type { TimeSeriesPoint } from './common'

/** Ordered stages of the signal → fill execution pipeline. */
export type ExecutionStageKey =
  | 'signal'
  | 'risk'
  | 'created'
  | 'sent'
  | 'received'
  | 'filled'
  | 'open'
  | 'closed'

export interface ExecutionStage {
  key: ExecutionStageKey
  label: string
  /** Median dwell time entering this stage (ms). */
  avgMs: number
  /** Orders that passed through this stage in the window. */
  count: number
  /** Drop-off vs the previous stage (rejections / risk blocks). */
  dropped: number
  status: 'ok' | 'warn' | 'fail'
}

/** Latency percentiles for one leg of the pipeline. */
export interface LatencyBucket {
  /** e.g. `Signal Delay`, `Execution Delay`, `Total Delay`. */
  label: string
  p50: number
  p90: number
  p95: number
  p99: number
}

export type ExecutionResult = 'filled' | 'rejected' | 'partial'

/** A single order's journey through the pipeline. */
export interface ExecutionFlowSample {
  id: string
  time: string
  symbol: string
  strategy: string
  signalMs: number
  riskMs: number
  execMs: number
  brokerMs: number
  fillMs: number
  totalMs: number
  result: ExecutionResult
}

export interface ExecutionData {
  stages: ExecutionStage[]
  latency: LatencyBucket[]
  recent: ExecutionFlowSample[]
  /** Orders processed per minute over the recent window. */
  throughput: TimeSeriesPoint[]
}
