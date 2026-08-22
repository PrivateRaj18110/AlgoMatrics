import { memo } from 'react'
import { Activity, Database, Network, Server, Zap } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { StatusDot } from '@/components/common/StatusDot'
import type { Status } from '@/types'
import { cn } from '@/utils/cn'
import { describeStatus } from '@/utils/status'

export interface HealthItem {
  label: string
  status: Status
  detail: string
  icon: 'machine' | 'broker' | 'execution' | 'database' | 'feed'
}

const ICONS = {
  machine: Server,
  broker: Network,
  execution: Zap,
  database: Database,
  feed: Activity,
} as const

/** Compact health strip summarising the major subsystems. */
export const SystemStatusBar = memo(function SystemStatusBar({ items }: { items: HealthItem[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {items.map((item) => {
        const Icon = ICONS[item.icon]
        const desc = describeStatus(item.status)
        return (
          <Card key={item.label} className="flex items-center gap-3 p-3">
            <div className={cn('flex size-9 items-center justify-center rounded-lg bg-muted', desc.text)}>
              <Icon className="size-4.5" />
            </div>
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <StatusDot status={item.status} />
                {item.label}
              </p>
              <p className={cn('truncate text-sm font-semibold', desc.text)}>{item.detail}</p>
            </div>
          </Card>
        )
      })}
    </div>
  )
})
