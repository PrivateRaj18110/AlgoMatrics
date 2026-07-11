import type { Severity, Status } from '@/types'
import { RESOURCE_THRESHOLDS } from './constants'

/** Visual descriptor for an operational status. */
export interface StatusDescriptor {
  label: string
  /** Tailwind text color utility. */
  text: string
  /** Tailwind background color utility (solid dot). */
  dot: string
  /** Badge variant name. */
  badge: 'success' | 'warning' | 'danger' | 'muted'
}

export const STATUS_MAP: Record<Status, StatusDescriptor> = {
  online: { label: 'Online', text: 'text-success', dot: 'bg-success', badge: 'success' },
  degraded: { label: 'Degraded', text: 'text-warning', dot: 'bg-warning', badge: 'warning' },
  offline: { label: 'Offline', text: 'text-danger', dot: 'bg-danger', badge: 'danger' },
}

export function describeStatus(status: Status): StatusDescriptor {
  return STATUS_MAP[status]
}

/** Roll several statuses into the most severe one (offline > degraded > online). */
export function worstStatus(statuses: Status[]): Status {
  if (statuses.some((s) => s === 'offline')) return 'offline'
  if (statuses.some((s) => s === 'degraded')) return 'degraded'
  return 'online'
}

/** Map a 0–100 resource utilisation to a status by threshold. */
export function resourceStatus(pct: number): Status {
  if (pct >= RESOURCE_THRESHOLDS.danger) return 'offline'
  if (pct >= RESOURCE_THRESHOLDS.warning) return 'degraded'
  return 'online'
}

/** Tailwind color utility for a resource bar fill based on utilisation. */
export function resourceBarColor(pct: number): string {
  if (pct >= RESOURCE_THRESHOLDS.danger) return 'bg-danger'
  if (pct >= RESOURCE_THRESHOLDS.warning) return 'bg-warning'
  return 'bg-success'
}

export const SEVERITY_MAP: Record<Severity, { label: string; badge: 'danger' | 'warning' | 'default' }> = {
  critical: { label: 'Critical', badge: 'danger' },
  warning: { label: 'Warning', badge: 'warning' },
  info: { label: 'Info', badge: 'default' },
}
