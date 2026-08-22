import { useEffect, useState } from 'react'

/**
 * Subscribe to a CSS media query. Used for responsive behaviour that can't be
 * expressed with Tailwind alone (e.g. auto-collapsing the sidebar on tablets).
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  )

  useEffect(() => {
    const mql = window.matchMedia(query)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)
    const timer = window.setTimeout(() => setMatches(mql.matches), 0)
    mql.addEventListener('change', handler)
    return () => {
      window.clearTimeout(timer)
      mql.removeEventListener('change', handler)
    }
  }, [query])

  return matches
}
