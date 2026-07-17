import type { RouteObject } from "react-router";
import { Navigate } from "react-router";

import { AppLayout } from "@/app/AppLayout";
import { RequireAdmin, RequireAuth } from "@/app/guards";
import { AdminPage } from "@/pages/AdminPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { AssistantPage } from "@/pages/AssistantPage";
import { AuditLogPage } from "@/pages/AuditLogPage";
import { BrokersPage } from "@/pages/BrokersPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage";
import { MarketIntelPage } from "@/pages/MarketIntelPage";
import { MarketPage } from "@/pages/MarketPage";
import { MarketplacePage } from "@/pages/MarketplacePage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { SettingsPage } from "@/pages/settings/SettingsPage";
import { StrategiesPage } from "@/pages/StrategiesPage";
import { StrategyDetailPage } from "@/pages/StrategyDetailPage";
import { SubscriptionPage } from "@/pages/SubscriptionPage";
import { TradingPage } from "@/pages/TradingPage";
import { WatchlistsPage } from "@/pages/WatchlistsPage";
import { VerifyEmailPage } from "@/pages/auth/VerifyEmailPage";
import { AcceptInvitationPage } from "@/pages/auth/AcceptInvitationPage";

export const router: RouteObject[] = [
  // The marketing landing page was removed; the site root is now the login page.
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  { path: "/verify-email", element: <VerifyEmailPage /> },
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
      { path: "/app/strategies", element: <StrategiesPage /> },
      { path: "/app/strategies/:strategyId", element: <StrategyDetailPage /> },
      { path: "/app/marketplace", element: <MarketplacePage /> },
      { path: "/app/assistant", element: <AssistantPage /> },
      { path: "/app/brokers", element: <BrokersPage /> },
      { path: "/app/trading", element: <TradingPage /> },
      { path: "/app/trading/:tab", element: <TradingPage /> },
      { path: "/app/market", element: <MarketPage /> },
      { path: "/app/market-intel", element: <MarketIntelPage /> },
      // The intraday workspace replaced the individual pages; old bookmarks
      // (and the retired backtesting page) redirect into it.
      { path: "/app/orders", element: <Navigate to="/app/trading/orders" replace /> },
      { path: "/app/positions", element: <Navigate to="/app/trading/positions" replace /> },
      { path: "/app/trades", element: <Navigate to="/app/trading/trades" replace /> },
      { path: "/app/portfolio", element: <Navigate to="/app/trading/portfolio" replace /> },
      { path: "/app/risk", element: <Navigate to="/app/trading/risk" replace /> },
      { path: "/app/backtesting", element: <Navigate to="/app/strategies" replace /> },
      { path: "/app/watchlists", element: <WatchlistsPage /> },
      { path: "/app/analytics", element: <AnalyticsPage /> },
      { path: "/app/notifications", element: <NotificationsPage /> },
      { path: "/app/audit", element: <AuditLogPage /> },
      { path: "/app/subscription", element: <SubscriptionPage /> },
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
