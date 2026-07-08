import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { AuthShell } from "@/pages/auth/AuthShell";

type State = "verifying" | "success" | "error";

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<State>(token ? "verifying" : "error");
  const [message, setMessage] = useState("This verification link is missing its token.");
  const attempted = useRef(false);

  useEffect(() => {
    if (!token || attempted.current) return;
    attempted.current = true;
    api("/auth/verify-email", { method: "POST", body: { token }, skipAuth: true })
      .then(() => setState("success"))
      .catch((error) => {
        setState("error");
        setMessage(error instanceof ApiError ? error.detail : "Verification failed.");
      });
  }, [token]);

  return (
    <AuthShell
      title="Verify your e-mail"
      footer={
        <Link to="/login" className="font-medium text-accent-500 hover:underline">
          Continue to sign in
        </Link>
      }
    >
      {state === "verifying" && (
        <div className="flex items-center gap-3 text-slate-500">
          <Spinner className="size-5 text-accent-500" /> Verifying your e-mail address…
        </div>
      )}
      {state === "success" && (
        <div className="rounded-lg border border-profit-500/40 bg-profit-500/10 px-4 py-6 text-center text-sm text-profit-600 dark:text-profit-400">
          Your e-mail address has been verified. You can now sign in.
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
