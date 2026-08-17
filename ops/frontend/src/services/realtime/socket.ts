import { USE_MOCK } from '../api/client'
import { mockEngine } from './engine'
import type { RealtimeHandler, RealtimeMessage, RealtimeTransport } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

function wsUrl(): string {
  const url = new URL(`${API_BASE_URL}/ws`, window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

class SocketTransport implements RealtimeTransport {
  connect(handler: RealtimeHandler): () => void {
    let socket: WebSocket | null = null
    let closed = false
    let retry = 0
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    const open = () => {
      if (closed) return
      // Do not embed RAJ_DASHBOARD_TOKEN / VITE_OPS_* in this bundle.
      socket = new WebSocket(wsUrl())
      socket.onmessage = (e) => {
        try {
          handler(JSON.parse(e.data) as RealtimeMessage)
        } catch {
          /* ignore malformed frames */
        }
      }
      socket.onopen = () => {
        retry = 0
      }
      socket.onclose = () => {
        if (closed) return
        retry = Math.min(retry + 1, 6)
        reconnectTimer = setTimeout(open, 1000 * retry)
      }
      socket.onerror = () => socket?.close()
    }

    open()
    return () => {
      closed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      socket?.close()
    }
  }
}

const socketTransport = new SocketTransport()

export const realtime: RealtimeTransport = USE_MOCK ? mockEngine : socketTransport
