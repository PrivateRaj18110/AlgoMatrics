import { zodResolver } from "@hookform/resolvers/zod";
import { clsx } from "clsx";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";

import { Glyph, type GlyphName } from "@/components/icons";
import { Seo } from "@/components/Seo";
import { Button, Field, Input, Textarea } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { AuthShell } from "@/pages/auth/AuthShell";

const TOPICS: Array<{ value: "access" | "support" | "partnership" | "other"; label: string; icon: GlyphName }> = [
  { value: "access", label: "Account access", icon: "lock" },
  { value: "support", label: "Support", icon: "alert" },
  { value: "partnership", label: "Partnership", icon: "rocket" },
  { value: "other", label: "Something else", icon: "mail" },
];

const schema = z.object({
  name: z.string().trim().min(1, "Your name is required").max(200),
  email: z.string().email("Enter a valid e-mail"),
  topic: z.enum(["access", "support", "partnership", "other"]),
  message: z.string().trim().min(10, "Tell us a little more (10+ characters)").max(5000),
  website: z.string().max(200).optional(),
});
type ContactForm = z.infer<typeof schema>;

export function ContactPage() {
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setValue,
    control,
    formState: { errors, isSubmitting },
  } = useForm<ContactForm>({
    resolver: zodResolver(schema),
    defaultValues: { topic: "access", message: "" },
  });
  const topic = useWatch({ control, name: "topic" });
  const message = useWatch({ control, name: "message" }) ?? "";

  async function onSubmit(values: ContactForm) {
    setFormError(null);
    try {
      await api("/contact", { method: "POST", body: values, skipAuth: true });
      setSent(true);
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? error.status === 429
            ? "You've sent a few messages already. Please try again in a few minutes."
            : error.detail
          : "Your message could not be sent.",
      );
    }
  }

  return (
    <AuthShell
      title={sent ? "Message sent" : "Contact us"}
      subtitle={sent ? undefined : "Questions about access, support or partnerships"}
    >
      <Seo
        title="Contact — ALGOMATRIC"
        description="Get in touch with the ALGOMATRIC team."
        canonicalPath="/contact"
      />
      {sent ? (
        <div className="space-y-5 text-center">
          <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-profit-500/10 text-profit-400 ring-1 ring-profit-500/25">
            <Glyph name="mail" className="size-6" />
          </span>
          <p className="text-sm leading-relaxed text-slate-300">
            Thanks — your message reached the team. We usually reply within one working day, to
            the e-mail address you gave.
          </p>
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-accent-400 hover:text-accent-300"
          >
            <Glyph name="arrowLeft" className="size-3.5" />
            Back to sign in
          </Link>
        </div>
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
          <fieldset>
            <legend className="mb-1.5 text-[13px] font-medium text-slate-300">Topic</legend>
            <div className="grid grid-cols-2 gap-2">
              {TOPICS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={topic === option.value}
                  onClick={() => setValue("topic", option.value, { shouldDirty: true })}
                  className={clsx(
                    "flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs font-medium transition-colors",
                    topic === option.value
                      ? "border-accent-400/60 bg-accent-500/10 text-accent-200"
                      : "border-white/10 text-slate-400 hover:border-white/20 hover:text-slate-200",
                  )}
                >
                  <Glyph name={option.icon} className="size-3.5" />
                  {option.label}
                </button>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" error={errors.name?.message} required>
              <Input {...register("name")} autoComplete="name" className="h-11" />
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
          </div>
          <Field label="Message" error={errors.message?.message} required>
            <Textarea {...register("message")} rows={5} className="resize-y" />
          </Field>
          <p className="-mt-2 text-right text-[11px] text-slate-500 tabular-nums">
            {message.length} / 5000
          </p>
          {/* Honeypot: invisible to people and screen readers, tempting to bots. */}
          <div aria-hidden className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
            <label>
              Website
              <input {...register("website")} tabIndex={-1} autoComplete="off" />
            </label>
          </div>
          <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
            Send message
            {!isSubmitting && <Glyph name="arrowRight" className="size-4" />}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
