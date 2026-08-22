import type { CategoryValue } from './common'

/** A consumed-vs-limit gauge (loss limits, exposure caps). */
export interface RiskLimit {
  label: string
  /** Amount consumed so far (absolute, same unit). */
  used: number
  /** Hard limit. */
  limit: number
  unit: 'currency' | 'percent'
}

/** Aggregated risk posture across the book. */
export interface RiskData {
  dailyLoss: RiskLimit
  weeklyLoss: RiskLimit
  monthlyLoss: RiskLimit
  /** Notional exposure currently deployed. */
  currentExposure: number
  /** Configured maximum notional exposure. */
  maxExposure: number
  /** Margin currently posted. */
  currentMargin: number
  marginLevelPct: number
  currentDrawdownPct: number
  maxDrawdownPct: number
  /** 1-day 95% value at risk. */
  valueAtRisk: number
  exposureBySymbol: CategoryValue[]
  exposureByStrategy: CategoryValue[]
  exposureByBroker: CategoryValue[]
}
