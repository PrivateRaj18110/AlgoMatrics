import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { SessionLoading } from "@/app/guards";
import { Glyph } from "@/components/icons";
import { Button, Field, Input, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { newPasswordSchema } from "@/lib/passwordPolicy";
import { AuthShell } from "@/pages/auth/AuthShell";
import { PasswordChecklist, RequestSubmitted } from "@/pages/auth/RequestAccessPage";
import { useAuth } from "@/stores/auth";
import type { InvitationPreview, Organization } from "@/types/api";

type State = "accepting" | "success" | "error";

function Notice({ tone, children }: { tone: "error" | "success"; children: React.ReactNode }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={
        tone === "error"
          ? "rounded-xl border border-loss-500/30 bg-loss-500/10 px-4 py-5 text-center text-sm text-loss-400"
          : "rounded-xl border border-profit-500/30 bg-profit-500/10 px-4 py-5 text-center text-sm text-profit-400"
      }
    >
      {children}
    </div>
  );
}

export function AcceptInvitationPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const status = useAuth((state) => state.status);

  if (!token) {
    return (
      <AuthShell title="Join organization" subtitle="Accept your ALGOMATRIC team invitation">
        <Notice tone="error">This invitation link is missing its token.</Notice>
      </AuthShell>
    );
  }
  if (status === "booting") return <SessionLoading label="CHECKING INVITATION..." />;
  if (status === "authenticated") return <AcceptAsMember token={token} />;
  return <JoinWithNewAccount token={token} />;
}

/** Signed in already: the invitation just becomes a membership. */
function AcceptAsMember({ token }: { token: string }) {
  const navigate = useNavigate();
  const loadContext = useAuth((state) => state.loadContext);
  const [state, setState] = useState<State>("accepting");
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [message, setMessage] = useState("The invitation could not be accepted.");
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;
    api<Organization>("/invitations/accept", {
      method: "POST",
      body: { token },
      skipOrg: true,
    })
      .then(async (accepted) => {
        setOrganization(accepted);
        await loadContext();
        setState("success");
      })
      .catch((error) => {
        setMessage(error instanceof ApiError ? error.detail : "The invitation could not be accepted.");
        setState("error");
      });
  }, [loadContext, token]);

  return (
    <AuthShell
      title="Join organization"
      subtitle="Accept your ALGOMATRIC team invitation"
      footer={
        <Link to="/app/dashboard" className="font-medium text-accent-400 hover:text-accent-300">
          Return to dashboard
        </Link>
      }
    >
      {state === "accepting" && (
        <div className="flex items-center gap-3 text-slate-400">
          <Spinner className="size-5 text-accent-400" />
          Validating your invitation…
        </div>
      )}
      {state === "success" && (
        <div className="space-y-4">
          <Notice tone="success">
            You joined {organization?.name ?? "the organization"} successfully.
          </Notice>
          <Button className="w-full" onClick={() => navigate("/app/dashboard", { replace: true })}>
            Open dashboard
          </Button>
        </div>
      )}
      {state === "error" && <Notice tone="error">{message}</Notice>}
    </AuthShell>
  );
}

const joinSchema = z
  .object({
    full_name: z.string().trim().min(1, "Your name is required").max(200),
    password: newPasswordSchema,
    confirm: z.string(),
  })
  .refine((values) => values.password === values.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  });
type JoinForm = z.infer<typeof joinSchema>;

/**
 * No session: show what the invitation is for and let the invitee create an
 * account from it. The link proves the address, so no separate verification;
 * the platform owner still approves the account before it can sign in.
 */
function JoinWithNewAccount({ token }: { token: string }) {
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const preview = useQuery({
    queryKey: ["invitation-preview", token],
    queryFn: () =>
      api<InvitationPreview>("/invitations/preview", { query: { token }, skipAuth: true }),
    retry: false,
  });
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<JoinForm>({ resolver: zodResolver(joinSchema), defaultValues: { password: "" } });
  const password = useWatch({ control, name: "password" }) ?? "";
  const returnTo = `/invitations/accept?token=${encodeURIComponent(token)}`;

  async function onSubmit(values: JoinForm) {
    setFormError(null);
    try {
      await api("/auth/request-access", {
        method: "POST",
        body: { invitation_token: token, full_name: values.full_name, password: values.password },
        skipAuth: true,
      });
      setSubmitted(true);
    } catch (error) {
      setFormError(error instanceof ApiError ? error.detail : "Your account could not be created.");
    }
  }

  const invite = preview.data;

  return (
    <AuthShell
      title={submitted ? "Account requested" : "You're invited"}
      subtitle={submitted ? undefined : "Create your account to join the team"}
    >
      {preview.isLoading && (
        <div className="flex items-center gap-3 text-slate-400">
          <Spinner className="size-5 text-accent-400" />
          Checking your invitation…
        </div>
      )}
      {preview.isError && (
        <Notice tone="error">
          {preview.error instanceof ApiError
            ? "This invitation is invalid or has expired. Ask for a new one."
            : "The invitation could not be checked right now."}
        </Notice>
      )}
      {invite && submitted && (
        <RequestSubmitted>
          <p className="text-slate-400">
            Once approved you will be in <span className="text-white">{invite.organization_name}</span>{" "}
            straight away.
          </p>
        </RequestSubmitted>
      )}
      {invite && !submitted && (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="flex items-start gap-3 rounded-xl border border-accent-500/20 bg-accent-500/[0.06] p-3.5">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-500/15 text-accent-300">
              <Glyph name="mail" />
            </span>
            <div className="min-w-0 text-sm">
              <p className="font-medium text-white">{invite.organization_name}</p>
              <p className="truncate text-xs text-slate-400">
                {invite.email} · joining as <span className="capitalize">{invite.role}</span>
              </p>
            </div>
          </div>
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
            Create account
          </Button>
          <p className="border-t border-white/[0.06] pt-5 text-center text-xs text-slate-500">
            Already have an account?{" "}
            <Link
              to="/login"
              state={{ returnTo }}
              className="font-medium text-accent-400 hover:text-accent-300"
            >
              Sign in to accept
            </Link>
          </p>
        </form>
      )}
    </AuthShell>
  );
}
