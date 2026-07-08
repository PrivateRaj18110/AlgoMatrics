import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router";
import { z } from "zod";

import { Button, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { AuthShell } from "@/pages/auth/AuthShell";

const schema = z
  .object({
    password: z
      .string()
      .min(10, "At least 10 characters")
      .regex(/[a-z]/, "Include a lowercase letter")
      .regex(/[A-Z]/, "Include an uppercase letter")
      .regex(/[0-9]/, "Include a digit"),
    confirm: z.string(),
  })
  .refine((data) => data.password === data.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  });
type Form = z.infer<typeof schema>;

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  async function onSubmit(values: Form) {
    setFormError(null);
    try {
      await api("/auth/reset-password", {
        method: "POST",
        skipAuth: true,
        body: { token, new_password: values.password },
      });
      setDone(true);
    } catch (error) {
      setFormError(error instanceof ApiError ? error.detail : "Reset failed");
    }
  }

  if (!token) {
    return (
      <AuthShell title="Invalid reset link" subtitle="This link is missing its token">
        <Link to="/forgot-password" className="text-accent-500 hover:underline">
          Request a new reset link
        </Link>
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell
        title="Password updated"
        subtitle="All active sessions were signed out"
        footer={
          <Link to="/login" className="font-medium text-accent-500 hover:underline">
            Sign in with your new password
          </Link>
        }
      >
        <div className="rounded-lg border border-profit-500/40 bg-profit-500/10 px-4 py-6 text-center text-sm text-profit-600 dark:text-profit-400">
          Your password has been changed successfully.
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Choose a new password" subtitle="Enter and confirm a strong password">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {formError && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {formError}
          </div>
        )}
        <Field label="New password" error={errors.password?.message} required>
          <Input {...register("password")} type="password" autoComplete="new-password" autoFocus />
        </Field>
        <Field label="Confirm password" error={errors.confirm?.message} required>
          <Input {...register("confirm")} type="password" autoComplete="new-password" />
        </Field>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Update password
        </Button>
      </form>
    </AuthShell>
  );
}
