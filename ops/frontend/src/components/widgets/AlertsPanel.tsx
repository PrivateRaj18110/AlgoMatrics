import { useMemo } from 'react'
import { ShieldCheck } from 'lucide-react'
import type { Alert } from '@/types'
import { ScrollArea } from '@/components/ui/scroll-area'
import { EmptyState } from '@/components/common/EmptyState'
import { AlertRow } from './AlertRow'

interface AlertsPanelProps {
  alerts: Alert[]
  /** Cap the number of rows shown (active alerts are prioritised). */
  limit?: number
  maxHeight?: number
}

/** Compact, prioritised alert list for the dashboard. */
export function AlertsPanel({ alerts, limit = 6, maxHeight = 360 }: AlertsPanelProps) {
  const ordered = useMemo(() => {
    const weight = { critical: 0, warning: 1, info: 2 } as const
    return [...alerts]
      .sort((a, b) => {
        if (a.acknowledged !== b.acknowledged) return a.acknowledged ? 1 : -1
        if (weight[a.severity] !== weight[b.severity]) return weight[a.severity] - weight[b.severity]
        return new Date(b.time).getTime() - new Date(a.time).getTime()
      })
      .slice(0, limit)
  }, [alerts, limit])

  if (ordered.length === 0) {
    return (
      <EmptyState icon={ShieldCheck} title="No active alerts" description="Systems nominal across all machines." />
    )
  }

  return (
    <ScrollArea style={{ maxHeight }}>
      <div className="space-y-2">
        {ordered.map((alert) => (
          <AlertRow key={alert.id} alert={alert} />
        ))}
      </div>
    </ScrollArea>
  )
}
