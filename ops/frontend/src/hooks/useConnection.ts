import { useEffect, useState } from 'react'
import { useIsFetching } from '@tanstack/react-query'
import type { ConnectionState } from '@/types'

/**
 * Derives a feed-connection indicator for the top bar from the browser's
 * online state and live query activity. When real-time transport (websockets)
 * is added later this hook is the single place to wire it in.
 */
export function useConnection(): ConnectionState {
  const fetching = useIsFetching()
  const [online, setOnline] = useState(() =>
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  )
  const [latencyMs, setLatencyMs] = useState(8)
  const [lastSync, setLastSync] = useState(() => new Date().toISOString())

  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  // Refresh the synthetic latency + last-sync stamp whenever a fetch settles.
  useEffect(() => {
    if (fetching === 0) {
      setLastSync(new Date().toISOString())
      setLatencyMs(6 + Math.round(Math.random() * 18))
    }
  }, [fetching])

  return {
    status: !online ? 'offline' : latencyMs > 200 ? 'degraded' : 'online',
    latencyMs,
    lastSync,
  }
}
