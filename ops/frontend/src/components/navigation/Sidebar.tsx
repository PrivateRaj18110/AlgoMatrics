import { PanelLeftClose, PanelLeftOpen, TerminalSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { MARKETS } from '@/types'
import { cn } from '@/utils/cn'
import { APP_NAME, APP_VERSION } from '@/utils/constants'
import { GLOBAL_NAV, MARKET_GROUPS, TOP_NAV, marketPath } from './navConfig'
import { NavItem } from './NavItem'

interface SidebarProps {
  collapsed: boolean
  /** Toggle desktop collapse. Omitted inside the mobile drawer. */
  onToggleCollapse?: () => void
  /** Called after navigating (used to close the mobile drawer). */
  onNavigate?: () => void
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center justify-between px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
      {children}
    </p>
  )
}

/** Sidebar contents, shared by the desktop rail and the mobile drawer. */
export function Sidebar({ collapsed, onToggleCollapse, onNavigate }: SidebarProps) {
  return (
    <div className="flex h-full flex-col bg-card">
      {/* Brand */}
      <div className={cn('flex h-14 items-center gap-2.5 border-b border-border px-4', collapsed && 'justify-center px-0')}>
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
          <TerminalSquare className="size-5" />
        </div>
        {!collapsed && (
          <div className="min-w-0 leading-tight">
            <p className="truncate text-sm font-semibold">{APP_NAME}</p>
            <p className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">
              Quant Trading OS
            </p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2 scrollbar-thin">
        {/* Top-level dashboard */}
        <NavItem
          to={TOP_NAV.to}
          label={TOP_NAV.label}
          icon={TOP_NAV.icon}
          end={TOP_NAV.end}
          collapsed={collapsed}
          onNavigate={onNavigate}
        />

        {/* Market namespaces — India / International, fully independent */}
        {MARKET_GROUPS.map((group) => (
          <div key={group.market}>
            {collapsed ? (
              <Separator className="my-2" />
            ) : (
              <SectionLabel>
                <span>{group.label}</span>
                <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] tracking-normal text-muted-foreground">
                  {MARKETS[group.market].currency}
                </span>
              </SectionLabel>
            )}
            {group.items.map((item) => (
              <NavItem
                key={`${group.market}-${item.segment}`}
                to={marketPath(group.market, item.segment)}
                label={collapsed ? `${MARKETS[group.market].shortLabel} · ${item.label}` : item.label}
                icon={item.icon}
                collapsed={collapsed}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        ))}

        {/* Global views */}
        {collapsed ? <Separator className="my-2" /> : <SectionLabel>Platform</SectionLabel>}
        {GLOBAL_NAV.map((item) => (
          <NavItem
            key={item.to}
            to={item.to}
            label={item.label}
            icon={item.icon}
            collapsed={collapsed}
            onNavigate={onNavigate}
          />
        ))}
      </nav>

      {/* Footer / collapse control */}
      <Separator />
      <div className={cn('flex items-center gap-2 p-2', collapsed ? 'flex-col' : 'justify-between px-3 py-2.5')}>
        {!collapsed && (
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            v{APP_VERSION}
          </span>
        )}
        {onToggleCollapse && (
          <Button
            variant="ghost"
            size="icon"
            className="size-8 text-muted-foreground"
            onClick={onToggleCollapse}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          </Button>
        )}
      </div>
    </div>
  )
}
