import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { Button, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { AuthShell } from "@/pages/auth/AuthShell";
import { useAuth } from "@/stores/auth";
import type { Organization } from "@/types/api";

type State = "accepting" | "success" | "error";

export function AcceptInvitationPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const loadContext = useAuth((state) => state.loadContext);
  const token = params.get("token") ?? "";
  const [state, setState] = useState<State>(token ? "accepting" : "error");
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [message, setMessage] = useState("This invitation link is missing its token.");
  const attempted = useRef(false);

  useEffect(() => {
    if (!token || attempted.current) return;
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
      subtitle="Accept your Algo Matrics team invitation"
      footer={
        <Link to="/app/dashboard" className="font-medium text-accent-500 hover:underline">
          Return to dashboard
        </Link>
      }
    >
      {state === "accepting" && (
        <div className="flex items-center gap-3 text-slate-500">
          <Spinner className="size-5 text-accent-500" />
          Validating your invitation…
        </div>
      )}
      {state === "success" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-profit-500/40 bg-profit-500/10 px-4 py-6 text-center text-sm text-profit-600 dark:text-profit-400">
            You joined {organization?.name ?? "the organization"} successfully.
          </div>
          <Button className="w-full" onClick={() => navigate("/app/dashboard", { replace: true })}>
            Open dashboard
          </Button>
        </div>
      )}
      {state === "error" && (
        <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-4 py-6 text-center text-sm text-loss-600 dark:text-loss-400">
          {message}
        </div>
      )}
    </AuthShell>
  );
}
