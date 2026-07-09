import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Modal,
  SkeletonRows,
  Table,
  Td,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useMobileDevices, useProfile, useUnregisterDevice } from "@/lib/hooks";
import { dateTime, timeAgo } from "@/lib/format";
import { useAuth } from "@/stores/auth";
import { toastSuccess } from "@/stores/toast";
import type { MfaEnrollment, SessionInfo, UserProfile } from "@/types/api";

function useSessions() {
  return useQuery({
    queryKey: ["sessions"],
    queryFn: () => api<SessionInfo[]>("/users/me/sessions", { skipOrg: true }),
  });
}

export function SecuritySettings() {
  const { data: profile } = useProfile();
  return (
    <div className="max-w-2xl space-y-6">
      <ChangePasswordCard />
      <MfaCard mfaEnabled={profile?.mfa_enabled ?? false} />
      <SessionsCard />
      <MobileDevicesCard />
    </div>
  );
}

function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    setSaving(true);
    try {
      await api("/users/me/password", {
        method: "POST",
        skipOrg: true,
        body: { current_password: current, new_password: next },
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      toastSuccess("Password changed", "Other sessions were signed out.");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Change failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Change password">
      <div className="space-y-3">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <Field label="Current password">
          <Input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} />
        </Field>
        <Field label="New password" hint="At least 10 characters with mixed case and a digit">
          <Input type="password" value={next} onChange={(event) => setNext(event.target.value)} />
        </Field>
        <Field label="Confirm new password">
          <Input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} />
        </Field>
        <Button onClick={submit} loading={saving}>
          Update password
        </Button>
      </div>
    </Card>
  );
}

function MfaCard({ mfaEnabled }: { mfaEnabled: boolean }) {
  const setUser = useAuth((state) => state.setUser);
  const client = useQueryClient();
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [disableOpen, setDisableOpen] = useState(false);

  async function refreshProfile() {
    const updated = await api<UserProfile>("/me", { skipOrg: true });
    setUser(updated);
    client.invalidateQueries({ queryKey: ["me"] });
  }

  return (
    <Card title="Two-factor authentication">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm">
            {mfaEnabled ? "MFA is enabled on your account." : "Add an extra layer of security."}
          </p>
          <Badge color={mfaEnabled ? "green" : "slate"} className="mt-1">
            {mfaEnabled ? "Enabled" : "Disabled"}
          </Badge>
        </div>
        {mfaEnabled ? (
          <Button variant="danger" size="sm" onClick={() => setDisableOpen(true)}>
            Disable MFA
          </Button>
        ) : (
          <Button size="sm" onClick={() => setEnrollOpen(true)}>
            Enable MFA
          </Button>
        )}
      </div>

      {enrollOpen && (
        <EnrollMfaModal
          onClose={() => setEnrollOpen(false)}
          onDone={() => {
            setEnrollOpen(false);
            void refreshProfile();
          }}
        />
      )}
      {disableOpen && (
        <DisableMfaModal
          onClose={() => setDisableOpen(false)}
          onDone={() => {
            setDisableOpen(false);
            void refreshProfile();
          }}
        />
      )}
    </Card>
  );
}

function EnrollMfaModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [enrollment, setEnrollment] = useState<MfaEnrollment | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function start() {
    setLoading(true);
    try {
      const result = await api<MfaEnrollment>("/users/me/mfa/enroll", {
        method: "POST",
        skipOrg: true,
      });
      setEnrollment(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to start enrollment");
    } finally {
      setLoading(false);
    }
  }

  async function activate() {
    setLoading(true);
    setError(null);
    try {
      await api("/users/me/mfa/activate", { method: "POST", skipOrg: true, body: { code } });
      toastSuccess("MFA enabled");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Invalid code");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Enable two-factor authentication">
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        {!enrollment ? (
          <>
            <p className="text-sm text-slate-500">
              Generate a secret, add it to your authenticator app, then confirm with a code.
            </p>
            <Button className="w-full" onClick={start} loading={loading}>
              Generate secret
            </Button>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-500">
              Add this secret to your authenticator app (or scan the otpauth URI), then enter the
              6-digit code.
            </p>
            <code className="block overflow-x-auto rounded-lg bg-slate-100 px-3 py-2 font-mono text-xs dark:bg-surface-800">
              {enrollment.secret}
            </code>
            <p className="text-xs break-all text-slate-400">{enrollment.provisioning_uri}</p>
            <Field label="Authentication code">
              <Input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                inputMode="numeric"
                placeholder="123456"
              />
            </Field>
            <Button className="w-full" onClick={activate} loading={loading}>
              Activate MFA
            </Button>
          </>
        )}
      </div>
    </Modal>
  );
}

function DisableMfaModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      await api("/users/me/mfa/disable", { method: "POST", skipOrg: true, body: { password, code } });
      toastSuccess("MFA disabled");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to disable");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Disable MFA">
      <div className="space-y-3">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <Field label="Password">
          <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </Field>
        <Field label="Authentication code">
          <Input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" />
        </Field>
        <Button className="w-full" variant="danger" onClick={submit} loading={loading}>
          Disable MFA
        </Button>
      </div>
    </Modal>
  );
}

function MobileDevicesCard() {
  const { data: devices, isLoading } = useMobileDevices();
  const unregister = useUnregisterDevice();

  async function revoke(id: string) {
    try {
      await unregister.mutateAsync(id);
      toastSuccess("Device unregistered");
    } catch {
      /* invalidation still refetches; surfacing is optional here */
    }
  }

  return (
    <Card title="Registered devices">
      {isLoading ? (
        <SkeletonRows rows={2} cols={3} />
      ) : !devices || devices.length === 0 ? (
        <EmptyState title="No mobile devices" body="Sign in on the mobile app to register a device." />
      ) : (
        <Table headers={["Device", "Platform", "Last seen", ""]}>
          {devices.map((device) => (
            <tr key={device.id}>
              <Td>
                <div className="max-w-xs truncate text-sm">
                  {device.device_name || "Unknown device"}
                  {device.app_version && (
                    <span className="ml-2 text-xs text-slate-400">v{device.app_version}</span>
                  )}
                </div>
              </Td>
              <Td>
                <Badge color="slate">{device.platform}</Badge>
              </Td>
              <Td className="text-xs text-slate-400">{timeAgo(device.last_seen_at)}</Td>
              <Td>
                <Button size="sm" variant="ghost" onClick={() => revoke(device.id)}>
                  Unregister
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function SessionsCard() {
  const { data: sessions, isLoading } = useSessions();
  const client = useQueryClient();

  async function revoke(id: string) {
    await api(`/users/me/sessions/${id}`, { method: "DELETE", skipOrg: true }).catch(() => undefined);
    client.invalidateQueries({ queryKey: ["sessions"] });
    toastSuccess("Session revoked");
  }

  async function revokeOthers() {
    await api("/users/me/sessions/revoke-others", { method: "POST", skipOrg: true }).catch(
      () => undefined,
    );
    client.invalidateQueries({ queryKey: ["sessions"] });
    toastSuccess("Other sessions revoked");
  }

  return (
    <Card
      title="Active sessions"
      actions={
        <Button size="sm" variant="secondary" onClick={revokeOthers}>
          Revoke others
        </Button>
      }
    >
      {isLoading ? (
        <SkeletonRows rows={2} cols={3} />
      ) : !sessions || sessions.length === 0 ? (
        <EmptyState title="No active sessions" />
      ) : (
        <Table headers={["Device", "Last seen", "Started", ""]}>
          {sessions.map((session) => (
            <tr key={session.id}>
              <Td>
                <div className="max-w-xs truncate text-sm">
                  {session.user_agent || "Unknown device"}
                  {session.is_current && (
                    <Badge color="green" className="ml-2">
                      This device
                    </Badge>
                  )}
                </div>
              </Td>
              <Td className="text-xs text-slate-400">{timeAgo(session.last_seen_at)}</Td>
              <Td className="text-xs text-slate-400">{dateTime(session.created_at)}</Td>
              <Td>
                {!session.is_current && (
                  <Button size="sm" variant="ghost" onClick={() => revoke(session.id)}>
                    Revoke
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
