import { memo } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { PnlValue } from '@/components/common/PnlValue'
import { DirectionBadge } from '@/components/widgets/TradeBadges'
import { EmptyState } from '@/components/common/EmptyState'
import type { Trade } from '@/types'
import { formatTime } from '@/utils/format'

interface RecentTradesTableProps {
  trades: Trade[]
  /** Constrain the scroll viewport height. */
  maxHeight?: number
}

/** Lightweight scrollable feed of the latest fills for the dashboard. */
export const RecentTradesTable = memo(function RecentTradesTable({
  trades,
  maxHeight = 360,
}: RecentTradesTableProps) {
  if (trades.length === 0) {
    return <EmptyState title="No recent trades" description="Executions will appear here in real time." />
  }

  return (
    <ScrollArea className="w-full" style={{ height: maxHeight }}>
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10 bg-card">
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">Symbol</th>
            <th className="px-3 py-2 font-medium">Side</th>
            <th className="hidden px-3 py-2 font-medium sm:table-cell">Strategy</th>
            <th className="px-3 py-2 text-right font-medium">PnL</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} className="border-b border-border/50 transition-colors hover:bg-accent/40">
              <td className="px-3 py-2 tabular text-muted-foreground">{formatTime(t.time)}</td>
              <td className="px-3 py-2 font-medium tabular">{t.symbol}</td>
              <td className="px-3 py-2">
                <DirectionBadge direction={t.direction} />
              </td>
              <td className="hidden px-3 py-2 text-muted-foreground sm:table-cell">
                <span className="line-clamp-1">{t.strategy}</span>
              </td>
              <td className="px-3 py-2 text-right">
                {t.status === 'cancelled' ? (
                  <span className="text-xs text-muted-foreground">—</span>
                ) : (
                  <PnlValue value={t.pnl} className="text-sm" />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollArea>
  )
})
