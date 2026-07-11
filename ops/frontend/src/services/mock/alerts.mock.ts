import type { Alert } from '@/types'

/**
 * Alert center fixtures. Mirrors the degraded / offline states baked into the
 * machine + strategy fixtures so the UI tells a consistent story.
 */
export const MOCK_ALERTS: Alert[] = [
  {
    id: 'alt-1',
    type: 'machine_offline',
    severity: 'critical',
    title: 'Machine offline',
    message: 'Personal Computer has missed 9 consecutive heartbeats.',
    source: 'Personal Computer',
    time: new Date(Date.now() - 9 * 60_000).toISOString(),
    acknowledged: false,
  },
  {
    id: 'alt-2',
    type: 'strategy_crash',
    severity: 'critical',
    title: 'Strategy crashed',
    message: 'Grid Hedge (GRID) exited unexpectedly with code 1.',
    source: 'Personal Computer · GRID',
    time: new Date(Date.now() - 11 * 60_000).toISOString(),
    acknowledged: false,
  },
  {
    id: 'alt-3',
    type: 'high_cpu',
    severity: 'warning',
    title: 'High CPU load',
    message: 'Google Cloud CPU sustained above 85% for 6 minutes.',
    source: 'Google Cloud',
    time: new Date(Date.now() - 4 * 60_000).toISOString(),
    acknowledged: false,
  },
  {
    id: 'alt-4',
    type: 'high_latency',
    severity: 'warning',
    title: 'Elevated broker latency',
    message: 'News Fade (NF) broker round-trip exceeded 250ms.',
    source: 'Google Cloud · NF',
    time: new Date(Date.now() - 7 * 60_000).toISOString(),
    acknowledged: false,
  },
  {
    id: 'alt-5',
    type: 'high_ram',
    severity: 'warning',
    title: 'Memory pressure',
    message: 'Google Cloud RAM usage climbing — 79% utilised.',
    source: 'Google Cloud',
    time: new Date(Date.now() - 16 * 60_000).toISOString(),
    acknowledged: true,
  },
  {
    id: 'alt-6',
    type: 'broker_offline',
    severity: 'critical',
    title: 'Broker session dropped',
    message: 'Binance FIX session re-connected after a 3s outage.',
    source: 'Google Cloud · Crypto Trend',
    time: new Date(Date.now() - 42 * 60_000).toISOString(),
    acknowledged: true,
  },
  {
    id: 'alt-7',
    type: 'high_latency',
    severity: 'info',
    title: 'Latency normalised',
    message: 'London VPS broker ping back under 5ms.',
    source: 'London VPS',
    time: new Date(Date.now() - 58 * 60_000).toISOString(),
    acknowledged: true,
  },
]
