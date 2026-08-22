import { useMemo } from 'react'
import type { HeatmapSeries } from '@/types'
import { cn } from '@/utils/cn'

interface HeatmapProps {
  series: HeatmapSeries
  /** `diverging` (red↔green around zero) for pnl, `sequential` (blue) for load. */
  mode?: 'diverging' | 'sequential'
  valueFormatter?: (value: number) => string
  className?: string
}

function cellColor(value: number, min: number, max: number, mode: 'diverging' | 'sequential'): string {
  if (mode === 'diverging') {
    const bound = Math.max(Math.abs(min), Math.abs(max)) || 1
    const intensity = Math.min(Math.abs(value) / bound, 1)
    const rgb = value >= 0 ? '34, 197, 94' : '239, 68, 68'
    return `rgba(${rgb}, ${(0.12 + intensity * 0.78).toFixed(2)})`
  }
  const span = max - min || 1
  const intensity = (value - min) / span
  return `rgba(37, 99, 235, ${(0.1 + intensity * 0.8).toFixed(2)})`
}

/** Compact value heatmap (weekday × hour, machine × hour, …). */
export function Heatmap({ series, mode = 'sequential', valueFormatter, className }: HeatmapProps) {
  const { min, max, lookup } = useMemo(() => {
    let lo = Infinity
    let hi = -Infinity
    const map = new Map<string, number>()
    for (const c of series.cells) {
      lo = Math.min(lo, c.value)
      hi = Math.max(hi, c.value)
      map.set(`${c.row}|${c.col}`, c.value)
    }
    return { min: lo, max: hi, lookup: map }
  }, [series])

  return (
    <div className={cn('w-full overflow-x-auto scrollbar-thin', className)}>
      <table className="w-full border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th className="w-16" />
            {series.cols.map((col) => (
              <th key={col} className="px-1 pb-1 text-center font-medium text-muted-foreground tabular">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {series.rows.map((row) => (
            <tr key={row}>
              <td className="pr-2 text-right font-medium text-muted-foreground whitespace-nowrap">
                {row}
              </td>
              {series.cols.map((col) => {
                const value = lookup.get(`${row}|${col}`) ?? 0
                return (
                  <td key={col} className="p-0">
                    <div
                      className="flex h-9 items-center justify-center rounded-sm tabular text-[10px] text-foreground/90"
                      style={{ backgroundColor: cellColor(value, min, max, mode) }}
                      title={`${row} · ${col}: ${valueFormatter ? valueFormatter(value) : value}`}
                    >
                      {valueFormatter ? valueFormatter(value) : value}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
