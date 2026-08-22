import { useMemo } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { AccountCard } from '@/components/cards/AccountCard'
import { PnlValue } from '@/components/common/PnlValue'
import { QueryState } from '@/components/common/QueryState'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useAccounts } from '@/hooks/useAccounts'
import { formatCompactCurrency } from '@/utils/format'
import type { Account } from '@/types'

function summarise(accounts: Account[]) {
  return {
    total: accounts.length,
    live: accounts.filter((a) => a.type === 'live').length,
    equity: accounts.reduce((s, a) => s + a.equity, 0),
    todayPnl: accounts.reduce((s, a) => s + a.todayPnl, 0),
  }
}

export default function AccountsPage() {
  const query = useAccounts()
  const stats = useMemo(() => (query.data ? summarise(query.data) : null), [query.data])

  return (
    <div className="space-y-5">
      <PageHeader
        title="Accounts"
        description="Live, prop and demo accounts with real-time equity and pnl."
      />

      {stats && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Accounts" value={String(stats.total)} />
          <Stat label="Live" value={`${stats.live}/${stats.total}`} />
          <Stat label="Total Equity" value={formatCompactCurrency(stats.equity)} />
          <Card className="p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Today PnL</p>
            <PnlValue value={stats.todayPnl} className="mt-2 block text-2xl" />
          </Card>
        </div>
      )}

      <QueryState
        query={query}
        loading={
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-72" />
            ))}
          </div>
        }
      >
        {(data) => (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.map((a) => (
              <AccountCard key={a.id} account={a} />
            ))}
          </div>
        )}
      </QueryState>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular">{value}</p>
    </Card>
  )
}
