import { NavLink } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/utils/cn'

interface NavItemProps {
  to: string
  label: string
  icon: LucideIcon
  /** Match the route exactly (used for the index "/" route). */
  end?: boolean
  collapsed: boolean
  /** Optional badge (e.g. unacknowledged alert count). */
  badge?: number
  onNavigate?: () => void
}

/** A single sidebar entry. Collapses to an icon with a tooltip on the rail. */
export function NavItem({ to, label, icon: Icon, end, collapsed, badge, onNavigate }: NavItemProps) {
  const link = (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors outline-none',
          'focus-visible:ring-2 focus-visible:ring-ring/60',
          collapsed && 'justify-center px-0',
          isActive
            ? 'bg-primary/15 text-primary'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground',
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn(
              'absolute left-0 h-5 w-0.5 rounded-r-full bg-primary transition-opacity',
              isActive ? 'opacity-100' : 'opacity-0',
            )}
          />
          <Icon className="size-4.5 shrink-0" />
          {!collapsed && <span className="flex-1 truncate">{label}</span>}
          {!collapsed && badge ? (
            <span className="rounded-full bg-danger px-1.5 text-[10px] font-semibold text-danger-foreground">
              {badge}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  )

  if (!collapsed) return link

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right" className="flex items-center gap-2">
        {label}
        {badge ? (
          <span className="rounded-full bg-danger px-1.5 text-[10px] font-semibold text-danger-foreground">
            {badge}
          </span>
        ) : null}
      </TooltipContent>
    </Tooltip>
  )
}
