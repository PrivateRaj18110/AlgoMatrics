import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Machine, SystemEvent } from '@/types'
import { realtime } from '@/services'
import { queryKeys } from './queryKeys'

const EVENT_LIMIT = 200
const MAX_BUFFERED = 400

/**
 * Single subscription to the realtime transport (mock engine or websocket).
 * Mounted once at the app shell, it folds live messages straight into the
 * TanStack Query cache so any page reading `useMachines` / `useEvents` updates
 * automatically — no per-page socket wiring required.
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
        case 'connection':
          // Heartbeat — surfaced by the top-bar connection indicator.
          break
      }
    })
  }, [qc])
}
