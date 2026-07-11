import type { Machine } from '@/types'
import { createRng, round } from './seed'

const rng = createRng(0x5eed01)

/**
 * Three reference hosts called out in the spec. Values are realistic snapshots;
 * a couple are intentionally degraded so the status colours / alerts are visible.
 */
export const MOCK_MACHINES: Machine[] = [
  {
    id: 'mch-london',
    name: 'London VPS',
    location: 'London · Equinix LD4',
    provider: 'Beeks Financial Cloud',
    status: 'online',
    cpu: round(34 + rng() * 10, 0),
    ram: round(58 + rng() * 8, 0),
    disk: round(46 + rng() * 5, 0),
    temperatureC: round(48 + rng() * 6, 0),
    internetMs: round(6 + rng() * 4, 0),
    brokerPingMs: round(2 + rng() * 3, 0),
    pythonStatus: 'online',
    uptimeSec: 32 * 86_400 + 4 * 3_600,
    lastHeartbeat: new Date(Date.now() - 4_000).toISOString(),
    strategyCount: 4,
  },
  {
    id: 'mch-gcloud',
    name: 'Google Cloud',
    location: 'europe-west2 · us-central1',
    provider: 'Google Cloud Platform',
    status: 'degraded',
    cpu: round(78 + rng() * 12, 0),
    ram: round(71 + rng() * 9, 0),
    disk: round(63 + rng() * 6, 0),
    temperatureC: null,
    internetMs: round(28 + rng() * 18, 0),
    brokerPingMs: round(34 + rng() * 22, 0),
    pythonStatus: 'online',
    uptimeSec: 11 * 86_400 + 9 * 3_600,
    lastHeartbeat: new Date(Date.now() - 12_000).toISOString(),
    strategyCount: 3,
  },
  {
    id: 'mch-pc',
    name: 'Personal Computer',
    location: 'Home Office · Mumbai',
    provider: 'On-premise',
    status: 'offline',
    cpu: 0,
    ram: round(12 + rng() * 4, 0),
    disk: round(72 + rng() * 5, 0),
    temperatureC: round(38 + rng() * 4, 0),
    internetMs: 0,
    brokerPingMs: 0,
    pythonStatus: 'offline',
    uptimeSec: 0,
    lastHeartbeat: new Date(Date.now() - 9 * 60_000).toISOString(),
    strategyCount: 2,
  },
]
