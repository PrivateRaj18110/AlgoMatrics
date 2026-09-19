// Security center: who is waiting to get in, who got in, who failed to, and
// which sessions are live right now. Platform-admin only (and MFA-gated server
// side). Everything here comes from one overview call.

import { clsx } from "clsx";
import { useState } from "react";

import { Glyph } from "@/components/icons";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  SkeletonRows,
  StatCard,
  Table,
  Td,
} from "@/components/ui";
import { ApiError, MFA_REQUIRED_CODE } from "@/lib/api";
import { describeDevice } from "@/lib/device";
import { dateTime, timeAgo } from "@/lib/format";
import {
  useApproveAccess,
  useRejectAccess,
  useRevokeSession,
  useSecurityOverview,
} from "@/lib/hooks";
import { toastError, toastSuccess } from "@/stores/toast";
import type { AccessRequest, ActiveSession } from "@/types/api";

function reasonLabel(reason: string): string {
  const map: Record<string, string> = {
    pending_approval: "Awaiting approval",
    email_unverified: "E-mail not verified",
    "invalid e-mail or password": "Wrong e-mail or password",
    "incorrect authentication code": "Wrong 2FA code",
  };
  return map[reason] ?? reason.charAt(0).toUpperCase() + reason.slice(1);
}

function Person({ name, email }: { name: string | null; email: string | null }) {
  return (
    <div className="min-w-0">
      <p className="truncate font-medium text-slate-800 dark:text-slate-100">{name ?? "Unknown"}</p>
      <p className="truncate text-xs text-slate-500 dark:text-slate-400">{email ?? "—"}</p>
    </div>
  );
}

function NetworkTag({ value }: { value: string | null }) {
  if (!value) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span
      className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600 dark:bg-white/[0.05] dark:text-slate-400"
      title="Hashed network tag. The same tag means the same network; the IP itself is never stored."
    >
      {value}
    </span>
  );
}

export function SecurityCenter() {
  const overview = useSecurityOverview();

  if (overview.isLoading) return <SkeletonRows rows={8} cols={4} />;
  if (overview.isError || !overview.data) {
    const mfa = overview.error instanceof ApiError && overview.error.code === MFA_REQUIRED_CODE;
    return (
      <Card>
        <EmptyState
          icon={<Glyph name={mfa ? "shield" : "alert"} className="size-5" />}
          title={mfa ? "Turn on two-factor authentication first" : "Security data is unavailable"}
          body={
            mfa
              ? "Administrator tools require 2FA on your account. Set it up under Settings → Security, then come back."
              : overview.error instanceof ApiError
                ? overview.error.detail
                : "The security overview could not be loaded."
          }
        />
      </Card>
    );
  }

  const data = overview.data;
  const { counts } = data;
  const adminsWithoutMfa = data.admins.filter((admin) => !admin.mfa_enabled);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Awaiting approval"
          value={counts.users_pending}
          icon={<Glyph name="clock" />}
          tone={counts.users_pending > 0 ? "amber" : "neutral"}
          sub={`${counts.users_active} active of ${counts.users_total} accounts`}
        />
        <StatCard
          label="Active sessions"
          value={counts.active_sessions}
          icon={<Glyph name="signal" />}
          tone="accent"
          sub={`${counts.users_suspended} suspended accounts`}
        />
        <StatCard
          label="Sign-ins · 24h"
          value={counts.sign_ins_24h}
          icon={<Glyph name="lock" />}
          tone="profit"
          sub="Successful, password and 2FA"
        />
        <StatCard
          label="Failed sign-ins · 24h"
          value={counts.failed_24h + counts.blocked_24h}
          icon={<Glyph name="alert" />}
          tone={counts.failed_24h + counts.blocked_24h > 0 ? "loss" : "neutral"}
          sub={`${counts.blocked_24h} blocked by lockout`}
        />
      </div>

      {!data.require_mfa_for_admins && (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/[0.07] p-4 text-sm text-amber-800 dark:text-amber-200">
          <Glyph name="alert" className="mt-0.5 size-4 text-amber-500" />
          The 2FA requirement for administrators is switched off on this server
          (REQUIRE_MFA_FOR_ADMINS=false).
        </div>
      )}

      <AccessRequests requests={data.access_requests} />

      <div className="grid gap-6 xl:grid-cols-3">
        <Card
          title="Administrator 2FA"
          subtitle={
            adminsWithoutMfa.length === 0
              ? "Every platform admin uses two-factor auth"
              : `${adminsWithoutMfa.length} admin(s) without 2FA`
          }
          icon={<Glyph name="shield" className="size-3.5" />}
          bodyClassName="p-2"
        >
          <ul>
            {data.admins.map((admin) => (
              <li
                key={admin.id}
                className="flex items-center justify-between gap-3 rounded-lg px-3 py-2.5"
              >
                <Person name={admin.full_name} email={admin.email} />
                <Badge color={admin.mfa_enabled ? "green" : "red"} dot>
                  {admin.mfa_enabled ? "2FA on" : "No 2FA"}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>

        <Card
          title="Recent sign-ins"
          subtitle="Newest first"
          icon={<Glyph name="lock" className="size-3.5" />}
          className="xl:col-span-2"
          bodyClassName="px-2 py-2"
        >
          {data.recent_sign_ins.length === 0 ? (
            <EmptyState title="No sign-ins recorded yet" />
          ) : (
            <Table headers={["Account", "When", "Method", "Device", "Network"]} dense>
              {data.recent_sign_ins.map((event, index) => (
                <tr key={`${event.occurred_at}-${index}`}>
                  <Td dense>
                    <Person name={event.full_name} email={event.email} />
                  </Td>
                  <Td dense className="text-xs text-slate-500 dark:text-slate-400">
                    <span title={dateTime(event.occurred_at)}>{timeAgo(event.occurred_at)}</span>
                  </Td>
                  <Td dense>
                    <Badge color={event.mfa ? "green" : "slate"}>
                      {event.mfa ? "Password + 2FA" : "Password"}
                    </Badge>
                  </Td>
                  <Td dense>
                    {event.new_device ? (
                      <Badge color="amber" dot>
                        New device
                      </Badge>
                    ) : (
                      <span className="text-xs text-slate-500">Known</span>
                    )}
                  </Td>
                  <Td dense>
                    <NetworkTag value={event.network} />
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      <Card
        title="Failed & blocked sign-ins"
        subtitle="Addresses are masked; the audit log keeps them this way permanently"
        icon={<Glyph name="alert" className="size-3.5" />}
        bodyClassName="px-2 py-2"
      >
        {data.failed_attempts.length === 0 ? (
          <EmptyState
            icon={<Glyph name="shield" className="size-5" />}
            title="No failed sign-ins"
            body="Nothing has been refused recently."
          />
        ) : (
          <Table headers={["Account", "When", "Step", "Reason", "Network", ""]} dense>
            {data.failed_attempts.map((attempt, index) => (
              <tr key={`${attempt.occurred_at}-${index}`}>
                <Td dense className="font-mono text-xs text-slate-700 dark:text-slate-200">
                  {attempt.email || "—"}
                </Td>
                <Td dense className="text-xs text-slate-500 dark:text-slate-400">
                  <span title={dateTime(attempt.occurred_at)}>{timeAgo(attempt.occurred_at)}</span>
                </Td>
                <Td dense className="text-xs uppercase text-slate-500">
                  {attempt.stage === "mfa" ? "2FA" : "Password"}
                </Td>
                <Td dense className="text-xs text-slate-600 dark:text-slate-300">
                  {reasonLabel(attempt.reason)}
                </Td>
                <Td dense>
                  <NetworkTag value={attempt.network} />
                </Td>
                <Td dense>
                  {attempt.blocked && (
                    <Badge color="red" dot>
                      Locked out
                    </Badge>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <ActiveSessions sessions={data.active_sessions} />
    </div>
  );
}

function AccessRequests({ requests }: { requests: AccessRequest[] }) {
  const approve = useApproveAccess();
  const reject = useRejectAccess();
  const [rejecting, setRejecting] = useState<AccessRequest | null>(null);

  const onApprove = (request: AccessRequest) =>
    approve.mutate(request.id, {
      onSuccess: () => toastSuccess("Access approved", `${request.email} can sign in now.`),
      onError: (error) =>
        toastError("Could not approve", error instanceof ApiError ? error.detail : undefined),
    });

  return (
    <Card
      title="Access requests"
      subtitle="Nobody can sign in with a new account until you approve it"
      icon={<Glyph name="inbox" className="size-3.5" />}
      className={clsx(requests.length > 0 && "ring-1 ring-amber-500/30")}
      bodyClassName="p-2"
      actions={
        requests.length > 0 ? (
          <Badge color="amber" dot>
            {requests.length} waiting
          </Badge>
        ) : null
      }
    >
      {requests.length === 0 ? (
        <EmptyState
          icon={<Glyph name="inbox" className="size-5" />}
          title="No one is waiting"
          body="New requests appear here and are e-mailed to every platform admin."
        />
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-white/[0.05]">
          {requests.map((request) => (
            <li
              key={request.id}
              className="flex flex-wrap items-center justify-between gap-3 px-3 py-3"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-semibold text-amber-600 ring-1 ring-amber-500/25 dark:text-amber-300">
                  {request.full_name.slice(0, 2).toUpperCase()}
                </span>
                <Person name={request.full_name} email={request.email} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-500" title={dateTime(request.requested_at)}>
                  requested {timeAgo(request.requested_at)}
                </span>
                <Badge color={request.email_verified ? "green" : "amber"}>
                  {request.email_verified ? "E-mail verified" : "E-mail not verified"}
                </Badge>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setRejecting(request)}
                  disabled={approve.isPending || reject.isPending}
                >
                  Reject
                </Button>
                <Button
                  size="sm"
                  variant="success"
                  onClick={() => onApprove(request)}
                  loading={approve.isPending && approve.variables === request.id}
                  disabled={reject.isPending}
                >
                  Approve
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={rejecting !== null}
        onClose={() => setRejecting(null)}
        title="Reject access request?"
        body={`${rejecting?.full_name ?? ""} (${rejecting?.email ?? ""}) will be told the request was not approved and will not be able to sign in.`}
        confirmLabel="Reject request"
        danger
        loading={reject.isPending}
        onConfirm={() => {
          if (!rejecting) return;
          const target = rejecting;
          reject.mutate(target.id, {
            onSuccess: () => {
              toastSuccess("Request rejected", target.email);
              setRejecting(null);
            },
            onError: (error) =>
              toastError("Could not reject", error instanceof ApiError ? error.detail : undefined),
          });
        }}
      />
    </Card>
  );
}

function ActiveSessions({ sessions }: { sessions: ActiveSession[] }) {
  const revoke = useRevokeSession();
  const [target, setTarget] = useState<ActiveSession | null>(null);

  return (
    <Card
      title="Active sessions"
      subtitle="Signing a session out also invalidates its refresh token immediately"
      icon={<Glyph name="signal" className="size-3.5" />}
      bodyClassName="px-2 py-2"
    >
      {sessions.length === 0 ? (
        <EmptyState title="No active sessions" />
      ) : (
        <Table headers={["Account", "Device", "Started", "Last active", ""]} dense>
          {sessions.map((session) => (
            <tr key={session.id}>
              <Td dense>
                <Person name={session.full_name} email={session.email} />
              </Td>
              <Td dense className="text-xs text-slate-600 dark:text-slate-300">
                <span title={session.user_agent}>{describeDevice(session.user_agent)}</span>
              </Td>
              <Td dense className="text-xs text-slate-500">
                {dateTime(session.created_at)}
              </Td>
              <Td dense className="text-xs text-slate-500">
                {timeAgo(session.last_seen_at)}
              </Td>
              <Td dense className="text-right">
                {session.is_current ? (
                  <Badge color="blue" dot>
                    This session
                  </Badge>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => setTarget(session)}>
                    Sign out
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      )}
      <ConfirmDialog
        open={target !== null}
        onClose={() => setTarget(null)}
        title="Sign this session out?"
        body={`${target?.email ?? ""} on ${describeDevice(target?.user_agent ?? "")} will be signed out and must sign in again.`}
        confirmLabel="Sign out session"
        danger
        loading={revoke.isPending}
        onConfirm={() => {
          if (!target) return;
          const session = target;
          revoke.mutate(session.id, {
            onSuccess: () => {
              toastSuccess("Session signed out", session.email);
              setTarget(null);
            },
            onError: (error) =>
              toastError("Could not sign out", error instanceof ApiError ? error.detail : undefined),
          });
        }}
      />
    </Card>
  );
}
