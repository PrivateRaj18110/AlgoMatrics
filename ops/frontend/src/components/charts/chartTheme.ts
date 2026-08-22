/** Shared Recharts styling tokens so every chart matches the terminal theme. */
export const CHART_COLORS = {
  primary: 'var(--color-chart-1)',
  success: 'var(--color-chart-2)',
  warning: 'var(--color-chart-3)',
  purple: 'var(--color-chart-4)',
  cyan: 'var(--color-chart-5)',
  grid: '#1f2937',
  axis: '#6b7280',
} as const

export const AXIS_TICK = {
  fill: '#9ca3af',
  fontSize: 11,
  fontFamily: 'var(--font-mono)',
} as const

export const CATEGORICAL_SERIES = [
  CHART_COLORS.primary,
  CHART_COLORS.success,
  CHART_COLORS.warning,
  CHART_COLORS.purple,
  CHART_COLORS.cyan,
]
