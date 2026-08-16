import { USE_MOCK } from '../api/client'
import { mockEngine } from './engine'
import type { RealtimeHandler, RealtimeMessage, RealtimeTransport } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

/** Subprotocol marker the backend expects before the credential value. */
const CREDENTIAL_SUBPROTOCOL = 'raj-token'

/**
 * Viewer credential for the telemetry websocket. The backend rejects the
 * handshake without it, so an unauthenticated client never receives a frame.
 */
const WS_TOKEN = import.meta.env.VITE_OPS_WS_TOKEN ?? import.meta.env.VITE_OPS_API_TOKEN ?? ''

/**
 * Derive the websocket URL from the configured API base URL. The base may be
 * relative (e.g. `/ops/api` behind the AlgoMatrics nginx), so resolve it
 * against the current page before swapping the protocol.
 */
function wsUrl(): string {
  const url = new URL(`${API_BASE_URL}/ws`, window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

/**
 * Carry the credential in `Sec-WebSocket-Protocol` rather than the query string.
 * Browsers cannot set headers on a `WebSocket`, and a token in the URL would
 * leak into access logs, proxy logs and `Referer` headers. Returning no
 * subprotocol when unconfigured lets the backend reject the connection cleanly
 * instead of the client sending an empty credential.
 */
function wsProtocols(): string[] | undefined {
  return WS_TOKEN ? [CREDENTIAL_SUBPROTOCOL, WS_TOKEN] : undefined
}

/**
 * Live websocket transport. Auto-reconnects with a capped backoff so a brief
 * backend blip doesn't permanently break the live feed.
 */
class SocketTransport implements RealtimeTransport {
  connect(handler: RealtimeHandler): () => void {
    let socket: WebSocket | null = null
    let closed = false
    let retry = 0
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    const open = () => {
      if (closed) return
      socket = new WebSocket(wsUrl(), wsProtocols())
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

/**
 * The active realtime transport. In mock mode this is the in-browser engine;
 * once a live backend is configured it is a reconnecting websocket. The rest
 * of the app only ever touches `realtime.connect(...)`.
 */
export const realtime: RealtimeTransport = USE_MOCK ? mockEngine : socketTransport
