import { Navigate, Outlet, useParams } from 'react-router-dom'
import { isMarket } from '@/types'
import { MarketProvider } from '@/providers/MarketProvider'

/**
 * Route guard for `/:market/*`. Validates the URL segment, then wraps the
 * nested market views in a <MarketProvider> so every page reads scoped data
 * and the correct currency. Unknown markets fall back to the dashboard.
 */
export function MarketLayout() {
  const { market } = useParams()

  if (!isMarket(market)) {
    return <Navigate to="/" replace />
  }

  return (
    <MarketProvider market={market}>
      <Outlet />
    </MarketProvider>
  )
}
