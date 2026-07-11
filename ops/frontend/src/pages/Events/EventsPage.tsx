import { useMemo, useState } from 'react'
import { Radio } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { EventTerminal } from '@/components/widgets/EventTerminal'
import { useEvents } from '@/hooks/useEvents'
import type { EventCategory } from '@/types'

type Filter = 'all' | EventCategory

const CATEGORIES: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All categories' },
  { value: 'trade', label: 'Trade' },
  { value: 'strategy', label: 'Strategy' },
  { value: 'machine', label: 'Machine' },
  { value: 'broker', label: 'Broker' },
  { value: 'risk', label: 'Risk' },
  { value: 'database', label: 'Database' },
  { value: 'system', label: 'System' },
]

export default function EventsPage() {
  const query = useEvents(200)
  const [filter, setFilter] = useState<Filter>('all')

  const filtered = useMemo(
    () => (query.data ?? []).filter((e) => filter === 'all' || e.category === filter),
    [query.data, filter],
  )

  return (
    <div className="flex h-[calc(100dvh-7rem)] min-h-[480px] flex-col space-y-4">
      <PageHeader
        title="Event Terminal"
        description="Live operational event stream — newest first."
        actions={
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-success">
              <Radio className="size-3.5 animate-pulse" />
              Live
            </span>
            <Select value={filter} onValueChange={(v) => setFilter(v as Filter)}>
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        }
      />

      <QueryState query={query} loading={<Skeleton className="h-full w-full" />}>
        {() => (
          <Panel
            title={`${filtered.length} events`}
            subtitle="Streaming"
            flush
            className="min-h-0 flex-1"
            bodyClassName="min-h-0"
          >
            <EventTerminal events={filtered} maxHeight="100%" />
          </Panel>
        )}
      </QueryState>
    </div>
  )
}
