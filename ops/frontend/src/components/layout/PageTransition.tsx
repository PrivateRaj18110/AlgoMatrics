import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { useLocation } from 'react-router-dom'

/**
 * Subtle route-change fade. Deliberately minimal (≈180ms, small offset) to stay
 * true to the "no unnecessary animations" terminal aesthetic while giving
 * navigation a sense of continuity. Keyed by pathname so each route re-enters.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  return (
    <motion.div
      key={pathname}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  )
}
