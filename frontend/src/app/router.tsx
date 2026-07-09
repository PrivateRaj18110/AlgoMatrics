import type { RouteObject } from "react-router";
import { Navigate } from "react-router";

import { AppLayout } from "@/app/AppLayout";
import { RequireAdmin, RequireAuth } from "@/app/guards";
import { AdminPage } from "@/pages/AdminPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { AssistantPage } from "@/pages/AssistantPage";
import { AuditLogPage } from "@/pages/AuditLogPage";
import { BacktestingPage } from "@/pages/BacktestingPage";
import { BrokersPage } from "@/pages/BrokersPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage";
import { LandingPage } from "@/pages/LandingPage";
import { MarketplacePage } from "@/pages/MarketplacePage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { OrdersPage } from "@/pages/OrdersPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { PositionsPage } from "@/pages/PositionsPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { RiskPage } from "@/pages/RiskPage";
import { SettingsPage } from "@/pages/settings/SettingsPage";
import { StrategiesPage } from "@/pages/StrategiesPage";
import { StrategyDetailPage } from "@/pages/StrategyDetailPage";
import { SubscriptionPage } from "@/pages/SubscriptionPage";
import { TradesPage } from "@/pages/TradesPage";
import { WatchlistsPage } from "@/pages/WatchlistsPage";
import { VerifyEmailPage } from "@/pages/auth/VerifyEmailPage";
import { AcceptInvitationPage } from "@/pages/auth/AcceptInvitationPage";

export const router: RouteObject[] = [
  { path: "/", element: <LandingPage /> },
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
      { path: "/app/backtesting", element: <BacktestingPage /> },
      { path: "/app/assistant", element: <AssistantPage /> },
      { path: "/app/brokers", element: <BrokersPage /> },
      { path: "/app/orders", element: <OrdersPage /> },
      { path: "/app/positions", element: <PositionsPage /> },
      { path: "/app/portfolio", element: <PortfolioPage /> },
      { path: "/app/trades", element: <TradesPage /> },
      { path: "/app/watchlists", element: <WatchlistsPage /> },
      { path: "/app/analytics", element: <AnalyticsPage /> },
      { path: "/app/notifications", element: <NotificationsPage /> },
      { path: "/app/audit", element: <AuditLogPage /> },
      { path: "/app/risk", element: <RiskPage /> },
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
