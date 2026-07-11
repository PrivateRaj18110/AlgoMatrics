import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { MarketLayout } from '@/components/layout/MarketLayout'

/*
 * Routes are code-split: each page is its own lazy chunk so the initial bundle
 * stays small. The Suspense boundary lives in <AppLayout>.
 *
 * Structure:
 *   /                  global cross-market dashboard
 *   /:market/*         India & International namespaces (independent data)
 *   /research          strategy lifecycle across markets
 *   /monitoring        multi-machine monitoring
 *   /settings          platform settings
 * Legacy flat paths redirect into the new structure for backwards compat.
 */
const DashboardPage = lazy(() => import('@/pages/Dashboard/DashboardPage'))

// Market-scoped views (rendered under <MarketLayout>).
const MarketOverviewPage = lazy(() => import('@/pages/market/MarketOverviewPage'))
const StrategiesPage = lazy(() => import('@/pages/Strategies/StrategiesPage'))
const LiveTradesPage = lazy(() => import('@/pages/market/LiveTradesPage'))
const ClosedTradesPage = lazy(() => import('@/pages/market/ClosedTradesPage'))
const PortfolioPage = lazy(() => import('@/pages/market/PortfolioPage'))
const MarketBrokersPage = lazy(() => import('@/pages/market/MarketBrokersPage'))
const MarketAnalyticsPage = lazy(() => import('@/pages/market/MarketAnalyticsPage'))
const MarketRiskPage = lazy(() => import('@/pages/market/MarketRiskPage'))
const MarketExecutionPage = lazy(() => import('@/pages/market/MarketExecutionPage'))

// Global / cross-cutting views.
const ResearchPage = lazy(() => import('@/pages/Research/ResearchPage'))
const MachinesPage = lazy(() => import('@/pages/Machines/MachinesPage'))
const SettingsPage = lazy(() => import('@/pages/Settings/SettingsPage'))
const LogsPage = lazy(() => import('@/pages/Logs/LogsPage'))
const AccountsPage = lazy(() => import('@/pages/Accounts/AccountsPage'))
const EventsPage = lazy(() => import('@/pages/Events/EventsPage'))
const AlertsPage = lazy(() => import('@/pages/Alerts/AlertsPage'))
const NotFound = lazy(() => import('@/pages/NotFound'))

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />

        {/* India / International — identical structure, fully independent data */}
        <Route path=":market" element={<MarketLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<MarketOverviewPage />} />
          <Route path="strategies" element={<StrategiesPage />} />
          <Route path="live-trades" element={<LiveTradesPage />} />
          <Route path="closed-trades" element={<ClosedTradesPage />} />
          <Route path="portfolio" element={<PortfolioPage />} />
          <Route path="brokers" element={<MarketBrokersPage />} />
          <Route path="analytics" element={<MarketAnalyticsPage />} />
          <Route path="risk" element={<MarketRiskPage />} />
          <Route path="execution" element={<MarketExecutionPage />} />
          <Route path="logs" element={<LogsPage />} />
        </Route>

        {/* Global views */}
        <Route path="research" element={<ResearchPage />} />
        <Route path="monitoring" element={<MachinesPage />} />
        <Route path="settings" element={<SettingsPage />} />

        {/* Backwards-compatible routes for existing bookmarks / deep links */}
        <Route path="machines" element={<Navigate to="/monitoring" replace />} />
        <Route path="accounts" element={<AccountsPage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="strategies" element={<Navigate to="/india/strategies" replace />} />
        <Route path="trades" element={<Navigate to="/india/closed-trades" replace />} />
        <Route path="execution" element={<Navigate to="/india/execution" replace />} />
        <Route path="risk" element={<Navigate to="/india/risk" replace />} />
        <Route path="analytics" element={<Navigate to="/india/analytics" replace />} />
        <Route path="brokers" element={<Navigate to="/india/brokers" replace />} />
        <Route path="logs" element={<Navigate to="/india/logs" replace />} />

        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
