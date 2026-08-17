import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Machine, SystemEvent, Trade } from '@/types'
import { realtime } from '@/services'
import { queryKeys } from './queryKeys'

const EVENT_LIMIT = 200
const MAX_BUFFERED = 400

function prependTrade(prev: Trade[] | undefined, trade: Trade): Trade[] {
  const rest = (prev ?? []).filter((row) => row.id !== trade.id)
  return [trade, ...rest].slice(0, MAX_BUFFERED)
}

/**
 * Single subscription to the realtime transport (mock engine or websocket).
 * Mounted once at the app shell, it folds live messages straight into the
 * TanStack Query cache so any page reading `useMachines` / `useEvents` updates
 * automatically — no per-page socket wiring required.
 *
 * Event routing is explicit: generic telemetry never enters the trades cache.
 * Only `{ type: 'trade' }` updates Closed / Live Trades.
 */
export function useRealtime() {
  const qc = useQueryClient()

  useEffect(() => {
    return realtime.connect((msg) => {
      switch (msg.type) {
        case 'machines':
          qc.setQueryData<Machine[]>(queryKeys.machines, msg.payload)
          break
        case 'event':
          qc.setQueryData<SystemEvent[]>(queryKeys.events(EVENT_LIMIT), (prev) =>
            [msg.payload, ...(prev ?? [])].slice(0, MAX_BUFFERED),
          )
          break
        case 'trade':
          qc.setQueriesData<Trade[]>({ queryKey: ['trades'] }, (prev) =>
            prependTrade(prev, msg.payload),
          )
          break
        case 'connection':
          // Heartbeat — surfaced by the top-bar connection indicator.
          break
      }
    })
  }, [qc])
}
