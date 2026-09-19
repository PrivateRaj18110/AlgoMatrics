import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router";
import { z } from "zod";

import { Glyph } from "@/components/icons";
import { Seo } from "@/components/Seo";
import { Button, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { AuthShell } from "@/pages/auth/AuthShell";
import { useAuth } from "@/stores/auth";
import { toastError } from "@/stores/toast";
import type { LoginResponse, Tokens } from "@/types/api";

const loginSchema = z.object({
  email: z.string().email("Enter a valid e-mail"),
  password: z.string().min(1, "Password is required"),
});
type LoginForm = z.infer<typeof loginSchema>;

const mfaSchema = z.object({ code: z.string().min(6, "6-digit code").max(8) });
type MfaForm = z.infer<typeof mfaSchema>;

const iconSlot = "pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-slate-500";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const setTokens = useAuth((state) => state.setTokens);
  const loadContext = useAuth((state) => state.loadContext);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });

  const mfaForm = useForm<MfaForm>({ resolver: zodResolver(mfaSchema) });

  async function finalize(tokens: Tokens) {
    setTokens(tokens);
    await loadContext();
    const candidate = (location.state as { returnTo?: unknown } | null)?.returnTo;
    const returnTo =
      typeof candidate === "string" &&
      candidate.startsWith("/") &&
      !candidate.startsWith("//")
        ? candidate
        : "/app/dashboard";
    navigate(returnTo, { replace: true });
  }

  async function onSubmit(values: LoginForm) {
    setFormError(null);
    setAwaitingApproval(false);
    try {
      const result = await api<LoginResponse>("/auth/login", {
        method: "POST",
        body: values,
        skipAuth: true,
      });
      if (result.kind === "mfa_required") {
        setMfaToken(result.mfa_token);
      } else if (result.tokens) {
        await finalize(result.tokens);
      }
    } catch (error) {
      const reason =
        error instanceof ApiError && error.errors && typeof error.errors === "object"
          ? (error.errors as { reason?: unknown }).reason
          : undefined;
      if (reason === "pending_approval") {
        setAwaitingApproval(true);
        return;
      }
      const message =
        error instanceof ApiError
          ? error.code === "authentication_failed" && error.detail.includes("not verified")
            ? "Please verify your e-mail address before signing in."
            : error.detail
          : "Login failed";
      setFormError(message);
    }
  }

  async function onMfaSubmit(values: MfaForm) {
    if (!mfaToken) return;
    try {
      const tokens = await api<Tokens>("/auth/mfa/complete", {
        method: "POST",
        body: { mfa_token: mfaToken, code: values.code },
        skipAuth: true,
      });
      await finalize(tokens);
    } catch (error) {
      toastError("Invalid code", error instanceof ApiError ? error.detail : undefined);
    }
  }

  if (mfaToken) {
    return (
      <AuthShell title="Two-factor authentication" subtitle="Enter the code from your authenticator app">
        <form onSubmit={mfaForm.handleSubmit(onMfaSubmit)} className="space-y-5" noValidate>
          <div className="flex items-center gap-3 rounded-xl border border-accent-500/20 bg-accent-500/[0.06] px-3.5 py-3 text-xs text-slate-300">
            <Glyph name="shield" className="size-4 text-accent-300" />
            Your account is protected with two-factor authentication.
          </div>
          <Field label="Authentication code" error={mfaForm.formState.errors.code?.message} required>
            <Input
              {...mfaForm.register("code")}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              autoFocus
              className="h-12 text-center font-mono text-lg tracking-[0.5em] placeholder:tracking-[0.5em]"
            />
          </Field>
          <Button type="submit" size="lg" className="w-full" loading={mfaForm.formState.isSubmitting}>
            Verify &amp; sign in
          </Button>
          <button
            type="button"
            onClick={() => setMfaToken(null)}
            className="flex w-full items-center justify-center gap-1.5 text-center text-sm text-slate-400 transition-colors hover:text-slate-200"
          >
            <Glyph name="arrowLeft" className="size-3.5" />
            Back to login
          </button>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your ALGOMATRIC console">
      <Seo title="Sign in — ALGOMATRIC" canonicalPath="/login" />
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
        {awaitingApproval && (
          <div
            role="status"
            className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-3 text-sm text-amber-200"
          >
            <Glyph name="clock" className="mt-0.5 size-4 text-amber-400" />
            <span>
              Your account is waiting for approval by the platform owner. You will get an e-mail
              as soon as it is approved.
            </span>
          </div>
        )}
        {formError && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-xl border border-loss-500/30 bg-loss-500/10 px-3.5 py-3 text-sm text-loss-400"
          >
            <Glyph name="alert" className="mt-0.5 size-4" />
            <span>{formError}</span>
          </div>
        )}
        <Field label="E-mail" error={errors.email?.message} required>
          <div className="relative">
            <Glyph name="mail" className={iconSlot} />
            <Input
              {...register("email")}
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              autoFocus
              className="h-11 pl-10"
            />
          </div>
        </Field>
        <div>
          <Field label="Password" error={errors.password?.message} required>
            <div className="relative">
              <Glyph name="lock" className={iconSlot} />
              <Input
                {...register("password")}
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="••••••••"
                className="h-11 pr-11 pl-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded-md p-2 text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-slate-200"
                aria-label={showPassword ? "Hide password" : "Show password"}
                aria-pressed={showPassword}
              >
                <Glyph name={showPassword ? "eyeOff" : "eye"} />
              </button>
            </div>
          </Field>
          <div className="mt-2 flex justify-end">
            <Link
              to="/forgot-password"
              className="text-xs font-medium text-accent-400 transition-colors hover:text-accent-300"
            >
              Forgot password?
            </Link>
          </div>
        </div>
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
          Sign in
          {!isSubmitting && <Glyph name="arrowRight" className="size-4" />}
        </Button>
        <p className="border-t border-white/[0.06] pt-5 text-center text-xs leading-relaxed text-slate-500">
          Don&apos;t have an account?{" "}
          <Link
            to="/request-access"
            className="font-medium text-accent-400 transition-colors hover:text-accent-300"
          >
            Request access
          </Link>
          <span className="mt-1 block text-slate-600">
            Every new account is approved by the platform owner.
          </span>
          <span className="mt-3 block">
            Need help?{" "}
            <Link
              to="/contact"
              className="font-medium text-slate-400 transition-colors hover:text-slate-200"
            >
              Contact us
            </Link>
          </span>
        </p>
      </form>
    </AuthShell>
  );
}
