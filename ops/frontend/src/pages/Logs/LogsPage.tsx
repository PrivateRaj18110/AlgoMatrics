import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { LogViewer } from '@/components/widgets/LogViewer'
import { useLogs } from '@/hooks/useLogs'
import type { LogLevel, LogSource } from '@/types'

const SOURCES: { value: LogSource; label: string }[] = [
  { value: 'application', label: 'Application' },
  { value: 'strategy', label: 'Strategy' },
  { value: 'python', label: 'Python' },
  { value: 'broker', label: 'Broker' },
  { value: 'database', label: 'Database' },
  { value: 'system', label: 'System' },
]

type LevelFilter = 'all' | LogLevel

export default function LogsPage() {
  const [source, setSource] = useState<LogSource>('application')
  const [level, setLevel] = useState<LevelFilter>('all')
  const [search, setSearch] = useState('')
  const query = useLogs(source)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (query.data ?? []).filter((l) => {
      if (level !== 'all' && l.level !== level) return false
      if (q && !l.message.toLowerCase().includes(q) && !l.logger.toLowerCase().includes(q)) return false
      return true
    })
  }, [query.data, level, search])

  return (
    <div className="flex h-[calc(100dvh-7rem)] min-h-[480px] flex-col space-y-4">
      <PageHeader
        title="Log Viewer"
        description="Application, strategy, python, broker, database and system streams."
        actions={
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter logs…"
                className="w-56 pl-8"
              />
            </div>
            <Select value={level} onValueChange={(v) => setLevel(v as LevelFilter)}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All levels</SelectItem>
                <SelectItem value="debug">Debug</SelectItem>
                <SelectItem value="info">Info</SelectItem>
                <SelectItem value="warn">Warn</SelectItem>
                <SelectItem value="error">Error</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      />

      <Tabs value={source} onValueChange={(v) => setSource(v as LogSource)}>
        <TabsList className="flex-wrap">
          {SOURCES.map((s) => (
            <TabsTrigger key={s.value} value={s.value}>
              {s.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <QueryState query={query} loading={<Skeleton className="h-full w-full" />}>
        {() => (
          <Panel
            title={SOURCES.find((s) => s.value === source)?.label + ' log'}
            subtitle={`${filtered.length} lines`}
            flush
            className="min-h-0 flex-1"
            bodyClassName="min-h-0"
          >
            <LogViewer logs={filtered} maxHeight="100%" />
          </Panel>
        )}
      </QueryState>
    </div>
  )
}
