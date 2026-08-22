import { useMemo, useState } from 'react'
import { Responsive, WidthProvider, type Layout, type Layouts } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import type { Alert, DashboardOverview, Trade } from '@/types'
import { Panel } from '@/components/layout/Panel'
import { EquityCurveChart } from '@/components/charts/EquityCurveChart'
import { DailyPnLChart } from '@/components/charts/DailyPnLChart'
import { PerformanceChart } from '@/components/charts/PerformanceChart'
import { RecentTradesTable } from '@/components/tables/RecentTradesTable'
import { AlertsPanel } from '@/components/widgets/AlertsPanel'

const ResponsiveGridLayout = WidthProvider(Responsive)

/** Panel order used when stacking on small breakpoints. */
const PANEL_ORDER = ['equity', 'alerts', 'daily', 'perf', 'trades'] as const

const LG_LAYOUT: Layout[] = [
  { i: 'equity', x: 0, y: 0, w: 8, h: 9, minW: 4, minH: 7 },
  { i: 'alerts', x: 8, y: 0, w: 4, h: 9, minW: 3, minH: 6 },
  { i: 'daily', x: 0, y: 9, w: 4, h: 8, minW: 3, minH: 6 },
  { i: 'perf', x: 4, y: 9, w: 4, h: 8, minW: 3, minH: 6 },
  { i: 'trades', x: 8, y: 9, w: 4, h: 8, minW: 3, minH: 6 },
]

/** Build a single-column stacked layout for narrow breakpoints. */
function stacked(cols: number): Layout[] {
  return PANEL_ORDER.map((i, idx) => ({ i, x: 0, y: idx * 8, w: cols, h: 8, minH: 6 }))
}

const LAYOUTS: Layouts = {
  lg: LG_LAYOUT,
  md: LG_LAYOUT,
  sm: stacked(6),
  xs: stacked(4),
  xxs: stacked(2),
}

interface DashboardGridProps {
  overview: DashboardOverview
  recentTrades: Trade[]
  alerts: Alert[]
}

/**
 * Draggable / resizable "command grid" of the core analytical panels.
 * Panels rearrange per breakpoint and can be dragged via their header handle.
 */
export function DashboardGrid({ overview, recentTrades, alerts }: DashboardGridProps) {
  const [layouts, setLayouts] = useState<Layouts>(LAYOUTS)

  const panels = useMemo(
    () => ({
      equity: (
        <Panel title="Equity Curve" subtitle="Account equity · last 60 sessions" dragHandle bodyClassName="p-2">
          <EquityCurveChart data={overview.equityCurve} height={260} />
        </Panel>
      ),
      alerts: (
        <Panel title="Alerts" subtitle="Prioritised by severity" dragHandle>
          <AlertsPanel alerts={alerts} maxHeight={250} />
        </Panel>
      ),
      daily: (
        <Panel title="Daily PnL" subtitle="Realised · last 30 sessions" dragHandle bodyClassName="p-2">
          <DailyPnLChart data={overview.dailyPnl} height={220} />
        </Panel>
      ),
      perf: (
        <Panel title="Performance" subtitle="Cumulative return %" dragHandle bodyClassName="p-2">
          <PerformanceChart data={overview.performance} height={220} />
        </Panel>
      ),
      trades: (
        <Panel title="Recent Trades" subtitle="Latest fills" dragHandle flush>
          <RecentTradesTable trades={recentTrades} maxHeight={236} />
        </Panel>
      ),
    }),
    [overview, recentTrades, alerts],
  )

  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={layouts}
      onLayoutChange={(_current, all) => setLayouts(all)}
      breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
      cols={{ lg: 12, md: 12, sm: 6, xs: 4, xxs: 2 }}
      rowHeight={30}
      margin={[16, 16]}
      containerPadding={[0, 0]}
      draggableHandle=".drag-handle"
      isBounded
      compactType="vertical"
    >
      {(Object.keys(panels) as Array<keyof typeof panels>).map((key) => (
        <div key={key} className="h-full">
          {panels[key]}
        </div>
      ))}
    </ResponsiveGridLayout>
  )
}
