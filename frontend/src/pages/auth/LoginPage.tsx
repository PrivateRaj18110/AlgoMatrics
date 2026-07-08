import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router";
import { z } from "zod";

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

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const setTokens = useAuth((state) => state.setTokens);
  const loadContext = useAuth((state) => state.loadContext);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

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
        <form onSubmit={mfaForm.handleSubmit(onMfaSubmit)} className="space-y-4" noValidate>
          <Field label="Authentication code" error={mfaForm.formState.errors.code?.message} required>
            <Input
              {...mfaForm.register("code")}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              autoFocus
            />
          </Field>
          <Button type="submit" className="w-full" loading={mfaForm.formState.isSubmitting}>
            Verify &amp; sign in
          </Button>
          <button
            type="button"
            onClick={() => setMfaToken(null)}
            className="w-full text-center text-sm text-slate-500 hover:underline"
          >
            Back to login
          </button>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your Algo Matrics account"
      footer={
        <>
          New here?{" "}
          <Link to="/register" className="font-medium text-accent-500 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {formError && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {formError}
          </div>
        )}
        <Field label="E-mail" error={errors.email?.message} required>
          <Input
            {...register("email")}
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            autoFocus
          />
        </Field>
        <Field label="Password" error={errors.password?.message} required>
          <Input {...register("password")} type="password" autoComplete="current-password" />
        </Field>
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-sm text-accent-500 hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Sign in
        </Button>
      </form>
    </AuthShell>
  );
}
