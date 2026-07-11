import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useTheme } from '@/providers/theme'

/** Dark / light theme switch (dark is the default terminal experience). */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-9 text-muted-foreground"
          onClick={toggleTheme}
          aria-label="Toggle theme"
        >
          {isDark ? <Moon className="size-4.5" /> : <Sun className="size-4.5" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{isDark ? 'Dark mode' : 'Light mode'}</TooltipContent>
    </Tooltip>
  )
}
