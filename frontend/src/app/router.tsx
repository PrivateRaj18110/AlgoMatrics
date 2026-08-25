import type { RouteObject } from "react-router";
import { Navigate, useParams } from "react-router";

import { INTERNATIONAL_MARKET_ENABLED } from "@/lib/marketRegion";

import { AppLayout } from "@/app/AppLayout";
import {
  OpsRedirect,
  RequireAdmin,
  RequireAnonymous,
  RequireAuth,
  RootRedirect,
} from "@/app/guards";
import { AdminPage } from "@/pages/AdminPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { AssistantPage } from "@/pages/AssistantPage";
import { AuditLogPage } from "@/pages/AuditLogPage";
import { CalendarPage } from "@/pages/CalendarPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage";
import { MarketIntelPage } from "@/pages/MarketIntelPage";
import { MarketPage } from "@/pages/MarketPage";
import { MarketSectionPage } from "@/pages/markets/MarketSectionPage";
import { MarketplacePage } from "@/pages/MarketplacePage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { PersonalHealthPage } from "@/pages/personalHealth/PersonalHealthPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { SettingsPage } from "@/pages/settings/SettingsPage";
import { StrategiesPage } from "@/pages/StrategiesPage";
import { StrategyDetailPage } from "@/pages/StrategyDetailPage";
import { TodoPage } from "@/pages/TodoPage";
import { TradingPage } from "@/pages/TradingPage";
import { WatchlistsPage } from "@/pages/WatchlistsPage";
import { VerifyEmailPage } from "@/pages/auth/VerifyEmailPage";
import { AcceptInvitationPage } from "@/pages/auth/AcceptInvitationPage";
import {
  ClosedTradesPage,
  EngineAnalyticsPage,
  EngineOrdersPage,
  EngineStrategiesPage,
  EngineStrategySymbolsRoute,
  EventsPage,
  LogsPage,
  MachinesPage,
  SystemHealthPage,
  TelemetryAlertsPage,
} from "@/pages/operations/OperationsPages";

export function InternationalRootRedirect() {
  return (
    <Navigate
      to={INTERNATIONAL_MARKET_ENABLED ? "/app/international/overview" : "/app/india/overview"}
      replace
    />
  );
}

export function InternationalRouteHandler() {
  const { section } = useParams();
  if (INTERNATIONAL_MARKET_ENABLED) {
    return <MarketSectionPage />;
  }
  if (section) {
    return <Navigate to={`/app/india/${section}`} replace />;
  }
  return <Navigate to="/app/india/overview" replace />;
}

export const router: RouteObject[] = [
  { path: "/", element: <RootRedirect /> },
  {
    path: "/login",
    element: (
      <RequireAnonymous>
        <LoginPage />
      </RequireAnonymous>
    ),
  },
  { path: "/register", element: <Navigate to="/login" replace /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  { path: "/verify-email", element: <VerifyEmailPage /> },
  { path: "/ops", element: <OpsRedirect /> },
  { path: "/ops/*", element: <OpsRedirect /> },
  {
    path: "/invitations/accept",
    element: (
      <RequireAuth>
        <AcceptInvitationPage />
      </RequireAuth>
    ),
  },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: "/app", element: <Navigate to="/app/dashboard" replace /> },
      { path: "/app/dashboard", element: <DashboardPage /> },
      { path: "/app/india", element: <Navigate to="/app/india/overview" replace /> },
      { path: "/app/india/:section", element: <MarketSectionPage /> },
      { path: "/app/international", element: <InternationalRootRedirect /> },
      { path: "/app/international/:section", element: <InternationalRouteHandler /> },
      { path: "/app/todo", element: <TodoPage /> },
      { path: "/app/calendar", element: <CalendarPage /> },
      { path: "/app/personal-health", element: <PersonalHealthPage /> },
      { path: "/app/strategies", element: <StrategiesPage /> },
      { path: "/app/strategies/:strategyId", element: <StrategyDetailPage /> },
      { path: "/app/engine-strategies", element: <EngineStrategiesPage /> },
      { path: "/app/engine-strategies/:strategyName", element: <EngineStrategySymbolsRoute /> },
      { path: "/app/machines", element: <MachinesPage /> },
      { path: "/app/system-health", element: <SystemHealthPage /> },
      { path: "/app/events", element: <EventsPage /> },
      { path: "/app/closed-trades", element: <ClosedTradesPage /> },
      { path: "/app/execution", element: <EngineOrdersPage /> },
      { path: "/app/logs", element: <LogsPage /> },
      { path: "/app/alerts", element: <TelemetryAlertsPage /> },
      { path: "/app/engine-analytics", element: <EngineAnalyticsPage /> },
      { path: "/app/marketplace", element: <MarketplacePage /> },
      { path: "/app/assistant", element: <AssistantPage /> },
      { path: "/app/brokers", element: <Navigate to="/app/settings/brokers" replace /> },
      { path: "/app/trading", element: <TradingPage /> },
      { path: "/app/trading/:tab", element: <TradingPage /> },
      { path: "/app/market", element: <Navigate to="/app/market-update" replace /> },
      { path: "/app/market-update", element: <MarketPage /> },
      { path: "/app/market-intel", element: <Navigate to="/app/market-intelligence" replace /> },
      { path: "/app/market-intelligence", element: <MarketIntelPage /> },
      { path: "/app/orders", element: <Navigate to="/app/trading/orders" replace /> },
      { path: "/app/positions", element: <Navigate to="/app/trading/positions" replace /> },
      { path: "/app/trades", element: <Navigate to="/app/trading/trades" replace /> },
      { path: "/app/portfolio", element: <Navigate to="/app/trading/portfolio" replace /> },
      { path: "/app/risk", element: <Navigate to="/app/trading/risk" replace /> },
      { path: "/app/backtesting", element: <Navigate to="/app/strategies" replace /> },
      { path: "/app/watchlists", element: <WatchlistsPage /> },
      { path: "/app/analytics", element: <AnalyticsPage /> },
      { path: "/app/notifications", element: <NotificationsPage /> },
      { path: "/app/audit", element: <Navigate to="/app/audit-log" replace /> },
      { path: "/app/audit-log", element: <AuditLogPage /> },
      { path: "/app/subscription", element: <Navigate to="/app/dashboard" replace /> },
      { path: "/app/settings", element: <SettingsPage /> },
      { path: "/app/settings/:section", element: <SettingsPage /> },
      {
        path: "/app/admin",
        element: (
          <RequireAdmin>
            <AdminPage />
          </RequireAdmin>
        ),
      },
      {
        path: "/app/admin/:section",
        element: (
          <RequireAdmin>
            <AdminPage />
          </RequireAdmin>
        ),
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];
