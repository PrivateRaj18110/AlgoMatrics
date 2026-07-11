import {
  LayoutDashboard,
  LineChart,
  Activity,
  History,
  Wallet,
  Network,
  BarChart3,
  ShieldAlert,
  Zap,
  ScrollText,
  FlaskConical,
  Server,
  Settings,
  type LucideIcon,
} from 'lucide-react'
import { MARKETS, MARKET_IDS, type Market } from '@/types'

export interface NavLeaf {
  /** Path segment relative to the market root, e.g. `overview`, `live-trades`. */
  segment: string
  label: string
  icon: LucideIcon
}

export interface NavTopItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

/**
 * The set of views available inside every market namespace. India and
 * International render the identical structure over completely independent
 * data. This is the single source of truth for both the sidebar groups and the
 * nested `/:market/*` routes.
 */
export const MARKET_NAV: NavLeaf[] = [
  { segment: 'overview', label: 'Overview', icon: LayoutDashboard },
  { segment: 'strategies', label: 'Strategies', icon: LineChart },
  { segment: 'live-trades', label: 'Live Trades', icon: Activity },
  { segment: 'closed-trades', label: 'Closed Trades', icon: History },
  { segment: 'portfolio', label: 'Portfolio', icon: Wallet },
  { segment: 'brokers', label: 'Brokers', icon: Network },
  { segment: 'analytics', label: 'Analytics', icon: BarChart3 },
  { segment: 'risk', label: 'Risk', icon: ShieldAlert },
  { segment: 'execution', label: 'Execution', icon: Zap },
  { segment: 'logs', label: 'Logs', icon: ScrollText },
]

/** A market group rendered as a labelled section in the sidebar. */
export interface MarketNavGroup {
  market: Market
  label: string
  items: NavLeaf[]
}

export const MARKET_GROUPS: MarketNavGroup[] = MARKET_IDS.map((market) => ({
  market,
  label: MARKETS[market].label.toUpperCase(),
  items: MARKET_NAV,
}))

/** Top-level entry above the market groups. */
export const TOP_NAV: NavTopItem = {
  to: '/',
  label: 'Dashboard',
  icon: LayoutDashboard,
  end: true,
}

/** Global entries rendered below the market groups. */
export const GLOBAL_NAV: NavTopItem[] = [
  { to: '/research', label: 'Research', icon: FlaskConical },
  { to: '/monitoring', label: 'Monitoring', icon: Server },
  { to: '/settings', label: 'Settings', icon: Settings },
]

/** Build the absolute path for a market view. */
export function marketPath(market: Market, segment: string): string {
  return `/${market}/${segment}`
}
