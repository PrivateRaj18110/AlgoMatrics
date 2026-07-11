import { memo, useMemo } from 'react'
import { AgGridReact } from 'ag-grid-react'
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
  type ValueFormatterParams,
} from 'ag-grid-community'
import type { Trade } from '@/types'
import { PnlValue } from '@/components/common/PnlValue'
import { DirectionBadge, TradeStatusBadge } from '@/components/widgets/TradeBadges'
import {
  formatCurrency,
  formatDateTime,
  formatDuration,
  formatLatency,
} from '@/utils/format'

// AG Grid v34 requires explicit module registration (community bundle).
ModuleRegistry.registerModules([AllCommunityModule])

/** Terminal-flavoured dark Quartz theme aligned with the design tokens. */
const rajGridTheme = themeQuartz.withParams({
  accentColor: '#2563EB',
  backgroundColor: '#111827',
  foregroundColor: '#E5E7EB',
  borderColor: '#1F2937',
  chromeBackgroundColor: '#0F1620',
  headerBackgroundColor: '#0F1620',
  headerTextColor: '#9CA3AF',
  oddRowBackgroundColor: '#0E141D',
  rowHoverColor: 'rgba(37, 99, 235, 0.08)',
  selectedRowBackgroundColor: 'rgba(37, 99, 235, 0.14)',
  fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
  fontSize: 13,
  headerFontSize: 11,
  cellHorizontalPadding: 12,
  rowHeight: 40,
  headerHeight: 38,
  wrapperBorderRadius: 12,
})

const priceFmt = (p: ValueFormatterParams<Trade, number>): string =>
  p.value == null ? '—' : p.value >= 1000 ? p.value.toFixed(1) : p.value.toFixed(4)

interface TradesTableProps {
  trades: Trade[]
  /** External quick filter text (search box lives on the page). */
  quickFilterText?: string
  height?: number | string
}

/** Professional trade blotter powered by AG Grid Community. */
export const TradesTable = memo(function TradesTable({
  trades,
  quickFilterText,
  height = '100%',
}: TradesTableProps) {
  const columnDefs = useMemo<ColDef<Trade>[]>(
    () => [
      {
        headerName: 'Time',
        field: 'time',
        valueFormatter: (p) => (p.value ? formatDateTime(p.value as string) : ''),
        minWidth: 130,
        sort: 'desc',
        cellClass: 'tabular',
      },
      { headerName: 'Strategy', field: 'strategy', minWidth: 150 },
      { headerName: 'Machine', field: 'machine', minWidth: 140, hide: false },
      { headerName: 'Broker', field: 'broker', minWidth: 130 },
      { headerName: 'Account', field: 'account', minWidth: 110, cellClass: 'tabular' },
      { headerName: 'Symbol', field: 'symbol', minWidth: 110, cellClass: 'tabular font-medium' },
      {
        headerName: 'Direction',
        field: 'direction',
        minWidth: 110,
        cellRenderer: (p: ICellRendererParams<Trade>) =>
          p.data ? <DirectionBadge direction={p.data.direction} /> : null,
      },
      {
        headerName: 'Entry',
        field: 'entry',
        type: 'rightAligned',
        minWidth: 100,
        valueFormatter: priceFmt,
        cellClass: 'tabular',
      },
      {
        headerName: 'Exit',
        field: 'exit',
        type: 'rightAligned',
        minWidth: 100,
        valueFormatter: priceFmt,
        cellClass: 'tabular',
      },
      {
        headerName: 'PnL',
        field: 'pnl',
        type: 'rightAligned',
        minWidth: 110,
        cellRenderer: (p: ICellRendererParams<Trade, number>) =>
          p.data && p.data.status !== 'cancelled' ? (
            <PnlValue value={p.value ?? 0} market={p.data.market} className="text-[13px]" />
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        headerName: 'Latency',
        field: 'latencyMs',
        type: 'rightAligned',
        minWidth: 100,
        valueFormatter: (p) => formatLatency((p.value as number) ?? 0),
        cellClass: 'tabular',
      },
      {
        headerName: 'Duration',
        field: 'durationSec',
        type: 'rightAligned',
        minWidth: 110,
        valueFormatter: (p) => formatDuration((p.value as number) ?? 0),
        cellClass: 'tabular',
      },
      {
        headerName: 'Status',
        field: 'status',
        minWidth: 120,
        cellRenderer: (p: ICellRendererParams<Trade>) =>
          p.data ? <TradeStatusBadge status={p.data.status} /> : null,
      },
    ],
    [],
  )

  const defaultColDef = useMemo<ColDef<Trade>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
      flex: 1,
    }),
    [],
  )

  return (
    <div style={{ height, width: '100%' }}>
      <AgGridReact<Trade>
        theme={rajGridTheme}
        rowData={trades}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        quickFilterText={quickFilterText}
        pagination
        paginationPageSize={25}
        paginationPageSizeSelector={[25, 50, 100]}
        animateRows={false}
        getRowId={(p) => p.data.id}
        tooltipShowDelay={300}
        suppressCellFocus
      />
    </div>
  )
})
