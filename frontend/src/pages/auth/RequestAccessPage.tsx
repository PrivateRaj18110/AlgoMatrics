import { zodResolver } from "@hookform/resolvers/zod";
import { clsx } from "clsx";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";

import { Glyph } from "@/components/icons";
import { Seo } from "@/components/Seo";
import { Button, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { PASSWORD_RULES, newPasswordSchema } from "@/lib/passwordPolicy";
import { AuthShell } from "@/pages/auth/AuthShell";

const schema = z
  .object({
    full_name: z.string().trim().min(1, "Your name is required").max(200),
    email: z.string().email("Enter a valid e-mail"),
    password: newPasswordSchema,
    confirm: z.string(),
  })
  .refine((values) => values.password === values.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  });
type RequestForm = z.infer<typeof schema>;

export function PasswordChecklist({ value }: { value: string }) {
  return (
    <ul className="mt-2 grid gap-1 text-xs">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(value);
        return (
          <li
            key={rule.label}
            className={clsx(
              "flex items-center gap-1.5 transition-colors",
              ok ? "text-profit-400" : "text-slate-500",
            )}
          >
            <span
              className={clsx(
                "flex size-3.5 items-center justify-center rounded-full ring-1",
                ok ? "bg-profit-500/15 ring-profit-500/40" : "ring-white/15",
              )}
              aria-hidden
            >
              {ok && <span className="size-1.5 rounded-full bg-profit-400" />}
            </span>
            {rule.label}
          </li>
        );
      })}
    </ul>
  );
}

export function RequestSubmitted({ children }: { children?: React.ReactNode }) {
  return (
    <div className="space-y-5 text-center">
      <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-accent-500/10 text-accent-300 ring-1 ring-accent-500/25">
        <Glyph name="shield" className="size-6" />
      </span>
      <div className="space-y-2 text-sm leading-relaxed text-slate-300">
        <p className="font-medium text-white">Your request is with the platform owner.</p>
        <p className="text-slate-400">
          Every new account is approved by hand. You will get an e-mail as soon as a decision is
          made. You cannot sign in before that.
        </p>
        {children}
      </div>
      <Link
        to="/login"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-accent-400 hover:text-accent-300"
      >
        <Glyph name="arrowLeft" className="size-3.5" />
        Back to sign in
      </Link>
    </div>
  );
}

export function RequestAccessPage() {
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<RequestForm>({ resolver: zodResolver(schema), defaultValues: { password: "" } });
  const password = useWatch({ control, name: "password" }) ?? "";

  async function onSubmit(values: RequestForm) {
    setFormError(null);
    try {
      await api("/auth/request-access", {
        method: "POST",
        body: { full_name: values.full_name, email: values.email, password: values.password },
        skipAuth: true,
      });
      setSubmitted(true);
    } catch (error) {
      setFormError(error instanceof ApiError ? error.detail : "The request could not be sent.");
    }
  }

  return (
    <AuthShell
      title={submitted ? "Request sent" : "Request access"}
      subtitle={
        submitted ? undefined : "The platform owner reviews and approves every new account"
      }
    >
      <Seo title="Request access — ALGOMATRIC" canonicalPath="/request-access" />
      {submitted ? (
        <RequestSubmitted>
          <p className="text-slate-400">
            Meanwhile, confirm your e-mail address using the link we just sent.
          </p>
        </RequestSubmitted>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {formError && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-xl border border-loss-500/30 bg-loss-500/10 px-3.5 py-3 text-sm text-loss-400"
            >
              <Glyph name="alert" className="mt-0.5 size-4" />
              <span>{formError}</span>
            </div>
          )}
          <Field label="Full name" error={errors.full_name?.message} required>
            <Input {...register("full_name")} autoComplete="name" autoFocus className="h-11" />
          </Field>
          <Field label="E-mail" error={errors.email?.message} required>
            <Input
              {...register("email")}
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              className="h-11"
            />
          </Field>
          <Field label="Password" error={errors.password?.message} required>
            <Input
              {...register("password")}
              type="password"
              autoComplete="new-password"
              className="h-11"
            />
          </Field>
          <PasswordChecklist value={password} />
          <Field label="Confirm password" error={errors.confirm?.message} required>
            <Input
              {...register("confirm")}
              type="password"
              autoComplete="new-password"
              className="h-11"
            />
          </Field>
          <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
            Send request
          </Button>
          <p className="border-t border-white/[0.06] pt-5 text-center text-xs text-slate-500">
            Already approved?{" "}
            <Link to="/login" className="font-medium text-accent-400 hover:text-accent-300">
              Sign in
            </Link>
          </p>
        </form>
      )}
    </AuthShell>
  );
}
