import type { Machine, SystemEvent, Trade } from '@/types'

/**
 * The realtime transport speaks a small, typed message protocol. The same
 * shapes are emitted by the client-side mock engine and by the FastAPI
 * websocket, so `useRealtime` is wired identically in mock and live mode.
 */
export type RealtimeMessage =
  | { type: 'machines'; payload: Machine[] }
  | { type: 'event'; payload: SystemEvent }
  | { type: 'trade'; payload: Trade }
  | { type: 'connection'; payload: { latencyMs: number; time: string } }

export type RealtimeHandler = (msg: RealtimeMessage) => void

/** A realtime transport: subscribe for messages, returns an unsubscribe fn. */
export interface RealtimeTransport {
  connect(handler: RealtimeHandler): () => void
}
