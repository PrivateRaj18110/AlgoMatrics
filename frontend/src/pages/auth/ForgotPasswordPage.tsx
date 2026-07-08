import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";

import { Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { AuthShell } from "@/pages/auth/AuthShell";

const schema = z.object({ email: z.string().email("Enter a valid e-mail") });
type Form = z.infer<typeof schema>;

export function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  async function onSubmit(values: Form) {
    // Always succeeds server-side to avoid account enumeration.
    await api("/auth/forgot-password", { method: "POST", body: values, skipAuth: true }).catch(
      () => undefined,
    );
    setSent(true);
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="We will e-mail you a reset link"
      footer={
        <Link to="/login" className="font-medium text-accent-500 hover:underline">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <div className="rounded-lg border border-accent-500/40 bg-accent-500/10 px-4 py-6 text-center text-sm text-accent-600 dark:text-accent-300">
          If an account exists for that e-mail, a reset link is on its way. The link expires in one
          hour.
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <Field label="E-mail" error={errors.email?.message} required>
            <Input {...register("email")} type="email" autoComplete="email" autoFocus />
          </Field>
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
