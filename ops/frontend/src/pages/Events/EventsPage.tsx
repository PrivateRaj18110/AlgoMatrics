import { useState } from 'react'
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
import { Input } from '@/components/ui/input'
import { EventTerminal } from '@/components/widgets/EventTerminal'
import { useEvents } from '@/hooks/useEvents'
import type { EventCategory, Severity } from '@/types'

type Filter = 'all' | EventCategory
type SeverityFilter = 'all' | Severity

const CATEGORIES: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All categories' },
  { value: 'trade', label: 'Trade' },
  { value: 'strategy', label: 'Strategy' },
  { value: 'machine', label: 'Machine' },
  { value: 'broker', label: 'Broker' },
  { value: 'risk', label: 'Risk' },
  { value: 'data', label: 'Data' },
  { value: 'database', label: 'Database' },
  { value: 'system', label: 'System' },
]

const SEVERITIES: { value: SeverityFilter; label: string }[] = [
  { value: 'all', label: 'All severities' },
  { value: 'info', label: 'Info' },
  { value: 'warning', label: 'Warning' },
  { value: 'critical', label: 'Critical' },
]

export default function EventsPage() {
  const [filter, setFilter] = useState<Filter>('all')
  const [severity, setSeverity] = useState<SeverityFilter>('all')
  const [eventType, setEventType] = useState('')
  const [symbol, setSymbol] = useState('')
  const query = useEvents(200, {
    category: filter === 'all' ? undefined : filter,
    severity: severity === 'all' ? undefined : severity,
    eventType: eventType.trim() || undefined,
    symbol: symbol.trim() || undefined,
  })
  const events = query.data ?? []

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
            <Select value={severity} onValueChange={(v) => setSeverity(v as SeverityFilter)}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SEVERITIES.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              value={eventType}
              onChange={(event) => setEventType(event.target.value)}
              placeholder="event type"
              className="h-9 w-36"
            />
            <Input
              value={symbol}
              onChange={(event) => setSymbol(event.target.value.toUpperCase())}
              placeholder="symbol"
              className="h-9 w-32"
            />
          </div>
        }
      />

      <QueryState query={query} loading={<Skeleton className="h-full w-full" />}>
        {() => (
          <Panel
            title={`${events.length} events`}
            subtitle="Streaming"
            flush
            className="min-h-0 flex-1"
            bodyClassName="min-h-0"
          >
            <EventTerminal events={events} maxHeight="100%" />
          </Panel>
        )}
      </QueryState>
    </div>
  )
}
