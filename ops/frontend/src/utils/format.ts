/**
 * Centralised formatting helpers. Keeping these in one place guarantees the
 * whole terminal renders money, percentages and timestamps identically.
 */

import { MARKETS, type Market } from '@/types'

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

const currencyFormatterPrecise = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** `$12,340` (or with a leading sign when `signed`). */
export function formatCurrency(value: number, opts?: { precise?: boolean; signed?: boolean }): string {
  const fmt = opts?.precise ? currencyFormatterPrecise : currencyFormatter
  const formatted = fmt.format(Math.abs(value))
  if (opts?.signed && value !== 0) {
    return `${value > 0 ? '+' : '-'}${formatted}`
  }
  return value < 0 ? `-${formatted}` : formatted
}

/** Compact money for axes / dense cards: `$12.3K`, `$1.2M`. */
export function formatCompactCurrency(value: number): string {
  const sign = value < 0 ? '-' : ''
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`
  return `${sign}$${abs.toFixed(0)}`
}

/* ----------------------------------------------------------------------------
 * Market-aware money formatting.
 *
 * Each market prices in its own currency (India → INR/en-IN, International →
 * USD/en-US). `Intl.NumberFormat` instances are cached per locale+currency so
 * formatting stays cheap on dense, frequently re-rendered grids.
 * ------------------------------------------------------------------------- */

const moneyFmtCache = new Map<string, Intl.NumberFormat>()

function moneyFormatter(market: Market, precise: boolean): Intl.NumberFormat {
  const meta = MARKETS[market]
  const key = `${meta.locale}:${meta.currency}:${precise ? 1 : 0}`
  let fmt = moneyFmtCache.get(key)
  if (!fmt) {
    fmt = new Intl.NumberFormat(meta.locale, {
      style: 'currency',
      currency: meta.currency,
      minimumFractionDigits: precise ? 2 : 0,
      maximumFractionDigits: precise ? 2 : 0,
    })
    moneyFmtCache.set(key, fmt)
  }
  return fmt
}

/** `₹12,34,500` / `$12,340` in the market's own currency. */
export function formatMoney(
  value: number,
  market: Market,
  opts?: { precise?: boolean; signed?: boolean },
): string {
  const formatted = moneyFormatter(market, !!opts?.precise).format(Math.abs(value))
  if (opts?.signed && value !== 0) {
    return `${value > 0 ? '+' : '-'}${formatted}`
  }
  return value < 0 ? `-${formatted}` : formatted
}

/**
 * Compact money for axes / dense cards, in the market's own scale.
 * India uses the lakh/crore system (`₹12.3L`, `₹1.2Cr`); everywhere else uses
 * K/M (`$12.3K`, `$1.2M`).
 */
export function formatCompactMoney(value: number, market: Market): string {
  const { currencySymbol: sym } = MARKETS[market]
  const sign = value < 0 ? '-' : ''
  const abs = Math.abs(value)
  if (market === 'india') {
    if (abs >= 1e7) return `${sign}${sym}${(abs / 1e7).toFixed(1)}Cr`
    if (abs >= 1e5) return `${sign}${sym}${(abs / 1e5).toFixed(1)}L`
    if (abs >= 1e3) return `${sign}${sym}${(abs / 1e3).toFixed(1)}K`
    return `${sign}${sym}${abs.toFixed(0)}`
  }
  if (abs >= 1e6) return `${sign}${sym}${(abs / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `${sign}${sym}${(abs / 1e3).toFixed(1)}K`
  return `${sign}${sym}${abs.toFixed(0)}`
}

/** `12.34%` with a configurable number of decimals. */
export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`
}

/** `+2.4%` / `-1.1%` — used for deltas. */
export function formatSignedPercent(value: number, decimals = 1): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(decimals)}%`
}

/** Plain number with thousands separators. */
export function formatNumber(value: number, decimals = 0): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/** Milliseconds → human latency string: `42ms`, `1.20s`. */
export function formatLatency(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  return `${Math.round(ms)}ms`
}

/** Seconds → `2d 4h 13m` style uptime. */
export function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86_400)
  const h = Math.floor((seconds % 86_400) / 3_600)
  const m = Math.floor((seconds % 3_600) / 60)
  const parts: string[] = []
  if (d) parts.push(`${d}d`)
  if (h) parts.push(`${h}h`)
  parts.push(`${m}m`)
  return parts.join(' ')
}

/** Seconds → trade duration string: `45s`, `12m 30s`, `1h 05m`. */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3_600) {
    const m = Math.floor(seconds / 60)
    const s = Math.round(seconds % 60)
    return `${m}m ${s.toString().padStart(2, '0')}s`
  }
  const h = Math.floor(seconds / 3_600)
  const m = Math.floor((seconds % 3_600) / 60)
  return `${h}h ${m.toString().padStart(2, '0')}m`
}

/** ISO timestamp → `14:32:05`. */
export function formatTime(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso
  return d.toLocaleTimeString('en-GB', { hour12: false })
}

/** ISO timestamp → `Jun 27, 14:32`. */
export function formatDateTime(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/** ISO timestamp → `Jun 27`. */
export function formatDateShort(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** Relative "time ago" for feeds / heartbeats: `just now`, `4m ago`, `2h ago`. */
export function formatRelativeTime(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso
  const diffMs = Date.now() - d.getTime()
  const sec = Math.round(diffMs / 1000)
  if (sec < 10) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  return `${day}d ago`
}
