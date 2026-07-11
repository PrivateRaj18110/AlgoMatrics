import type { Machine } from '@/types'
import { MOCK_MACHINES } from '../mock/machines.mock'
import { buildEvent } from '../mock/events.mock'
import type { RealtimeHandler, RealtimeMessage, RealtimeTransport } from './types'

/**
 * Client-side mock engine — makes the terminal feel alive without a backend.
 *
 * A single shared interval mutates machine telemetry (CPU / RAM / pings),
 * emits a steady trickle of system events and a connection heartbeat. The
 * engine is reference-counted: it only runs while at least one subscriber is
 * connected, so it never burns cycles on idle routes.
 */
class MockEngine implements RealtimeTransport {
  private handlers = new Set<RealtimeHandler>()
  private timer: ReturnType<typeof setInterval> | null = null
  private machines: Machine[] = structuredClone(MOCK_MACHINES)
  private seq = 0

  connect(handler: RealtimeHandler): () => void {
    this.handlers.add(handler)
    if (!this.timer) this.start()
    return () => {
      this.handlers.delete(handler)
      if (this.handlers.size === 0) this.stop()
    }
  }

  private start() {
    this.timer = setInterval(() => this.tick(), 3_000)
  }

  private stop() {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }

  private emit(msg: RealtimeMessage) {
    this.handlers.forEach((h) => h(msg))
  }

  /** Clamp helper. */
  private jitter(value: number, delta: number, min: number, max: number): number {
    return Math.round(Math.max(min, Math.min(max, value + (Math.random() - 0.5) * 2 * delta)))
  }

  private tick() {
    this.seq += 1

    // 1. Mutate machine telemetry for online / degraded hosts.
    this.machines = this.machines.map((m) => {
      if (m.status === 'offline') return m
      return {
        ...m,
        cpu: this.jitter(m.cpu, 6, 4, 99),
        ram: this.jitter(m.ram, 3, 8, 98),
        internetMs: this.jitter(m.internetMs, 4, 2, 240),
        brokerPingMs: this.jitter(m.brokerPingMs, 5, 1, 280),
        temperatureC: m.temperatureC != null ? this.jitter(m.temperatureC, 2, 30, 92) : null,
        lastHeartbeat: new Date().toISOString(),
      }
    })
    this.emit({ type: 'machines', payload: structuredClone(this.machines) })

    // 2. Emit a connection heartbeat every tick.
    this.emit({
      type: 'connection',
      payload: { latencyMs: 4 + Math.round(Math.random() * 22), time: new Date().toISOString() },
    })

    // 3. Emit a fresh event roughly every other tick.
    if (Math.random() < 0.6) {
      this.emit({ type: 'event', payload: buildEvent(0, `evt-live-${Date.now()}-${this.seq}`) })
    }
  }
}

export const mockEngine = new MockEngine()
