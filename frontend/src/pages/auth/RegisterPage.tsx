import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";

import { Seo } from "@/components/Seo";
import { Button, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { AuthShell } from "@/pages/auth/AuthShell";

const schema = z
  .object({
    full_name: z.string().min(1, "Your name is required").max(200),
    organization_name: z.string().max(200).optional(),
    email: z.string().email("Enter a valid e-mail"),
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
type RegisterForm = z.infer<typeof schema>;

export function RegisterPage() {
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterForm>({ resolver: zodResolver(schema) });

  async function onSubmit(values: RegisterForm) {
    setFormError(null);
    try {
      await api("/auth/register", {
        method: "POST",
        skipAuth: true,
        body: {
          full_name: values.full_name,
          organization_name: values.organization_name || null,
          email: values.email,
          password: values.password,
        },
      });
      setDone(true);
    } catch (error) {
      setFormError(error instanceof ApiError ? error.detail : "Registration failed");
    }
  }

  if (done) {
    return (
      <AuthShell
        title="Check your inbox"
        subtitle="We sent a verification link to activate your account"
        footer={
          <Link to="/login" className="font-medium text-accent-500 hover:underline">
            Continue to sign in
          </Link>
        }
      >
        <div className="rounded-lg border border-profit-500/40 bg-profit-500/10 px-4 py-6 text-center text-sm text-profit-600 dark:text-profit-400">
          Your account was created. Open the verification e-mail (in local development it is printed
          to the API logs) and follow the link to activate your account.
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start with paper trading in minutes"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-accent-500 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <Seo
        title="Create a free account — Algo Matrics"
        description="Create a free Algo Matrics account and start with deterministic paper trading: one paper broker connection and one active strategy, at no cost."
        canonicalPath="/register"
      />
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {formError && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {formError}
          </div>
        )}
        <Field label="Full name" error={errors.full_name?.message} required>
          <Input {...register("full_name")} autoComplete="name" placeholder="Jane Trader" />
        </Field>
        <Field
          label="Organization (optional)"
          error={errors.organization_name?.message}
          hint="Leave blank to auto-create a personal workspace"
        >
          <Input {...register("organization_name")} placeholder="Acme Capital" />
        </Field>
        <Field label="E-mail" error={errors.email?.message} required>
          <Input {...register("email")} type="email" autoComplete="email" placeholder="you@example.com" />
        </Field>
        <Field label="Password" error={errors.password?.message} required>
          <Input {...register("password")} type="password" autoComplete="new-password" />
        </Field>
        <Field label="Confirm password" error={errors.confirm?.message} required>
          <Input {...register("confirm")} type="password" autoComplete="new-password" />
        </Field>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}
