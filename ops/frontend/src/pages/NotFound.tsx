import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** 404 fallback for unmatched routes. */
export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <div className="rounded-full bg-muted p-4 text-muted-foreground">
        <Compass className="size-7" />
      </div>
      <div>
        <p className="text-2xl font-semibold tracking-tight">Page not found</p>
        <p className="mt-1 text-sm text-muted-foreground">
          The view you’re looking for doesn’t exist or has moved.
        </p>
      </div>
      <Button asChild>
        <Link to="/">Back to dashboard</Link>
      </Button>
    </div>
  )
}
