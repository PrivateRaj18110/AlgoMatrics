import { useEffect, useState } from 'react'

/** Ticking wall clock for the top bar. Updates once per second. */
export function useClock(): Date {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])

  return now
}
