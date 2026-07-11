/** User-facing application settings, persisted to localStorage. */

export type ThemeMode = 'dark' | 'light'

/** Outbound notification transports. */
export interface NotificationChannels {
  telegram: boolean
  browser: boolean
  email: boolean
}

export interface AppSettings {
  workspaceName: string
  theme: ThemeMode
  /** View auto-refresh cadence in seconds. */
  refreshIntervalSec: number
  baseCurrency: string
  timezone: string
  apiBaseUrl: string
  channels: NotificationChannels
  /** Per-rule notification toggles. */
  notifyMachineOffline: boolean
  notifyHighResource: boolean
  notifyBrokerDisconnect: boolean
  notifyStrategyCrash: boolean
  /** Appearance toggles. */
  denseTables: boolean
  heartbeatPulse: boolean
}

export const DEFAULT_SETTINGS: AppSettings = {
  workspaceName: 'Raj Quant OS',
  theme: 'dark',
  refreshIntervalSec: 30,
  baseCurrency: 'USD',
  timezone: 'utc',
  apiBaseUrl: '',
  channels: { telegram: false, browser: false, email: false },
  notifyMachineOffline: true,
  notifyHighResource: true,
  notifyBrokerDisconnect: true,
  notifyStrategyCrash: true,
  denseTables: true,
  heartbeatPulse: true,
}
