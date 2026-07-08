import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Modal,
  Select,
  SkeletonRows,
  Table,
  Td,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useInvitations, useMembers } from "@/lib/hooks";
import { dateOnly } from "@/lib/format";
import { activeOrg } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";

export function TeamSettings() {
  const { data: members, isLoading } = useMembers();
  const { data: invitations } = useInvitations();
  const [inviteOpen, setInviteOpen] = useState(false);
  const client = useQueryClient();
  const org = activeOrg();
  const canManage = org?.role === "owner" || org?.role === "admin";

  function invalidate() {
    client.invalidateQueries({ queryKey: ["members"] });
    client.invalidateQueries({ queryKey: ["invitations"] });
  }

  async function changeRole(membershipId: string, role: string) {
    try {
      await api(`/members/${membershipId}`, { method: "PATCH", body: { role } });
      invalidate();
      toastSuccess("Role updated");
    } catch (error) {
      toastError("Update failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function removeMember(membershipId: string) {
    try {
      await api(`/members/${membershipId}`, { method: "DELETE" });
      invalidate();
      toastSuccess("Member removed");
    } catch (error) {
      toastError("Remove failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function revokeInvite(id: string) {
    try {
      await api(`/members/invitations/${id}`, { method: "DELETE" });
      invalidate();
      toastSuccess("Invitation revoked");
    } catch (error) {
      toastError("Revoke failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <div className="space-y-6">
      <Card
        title="Team members"
        actions={
          canManage && (
            <Button size="sm" onClick={() => setInviteOpen(true)}>
              Invite member
            </Button>
          )
        }
      >
        {isLoading ? (
          <SkeletonRows rows={3} cols={4} />
        ) : !members || members.length === 0 ? (
          <EmptyState title="No members" />
        ) : (
          <Table headers={["Member", "Role", "Joined", ""]}>
            {members.map((member) => (
              <tr key={member.membership_id}>
                <Td>
                  <div>
                    <p className="font-medium">{member.full_name}</p>
                    <p className="text-xs text-slate-400">{member.email}</p>
                  </div>
                </Td>
                <Td>
                  {canManage && member.role !== "owner" ? (
                    <Select
                      value={member.role}
                      onChange={(event) => changeRole(member.membership_id, event.target.value)}
                      className="w-28"
                    >
                      <option value="admin">Admin</option>
                      <option value="trader">Trader</option>
                      <option value="viewer">Viewer</option>
                    </Select>
                  ) : (
                    <Badge color={member.role === "owner" ? "violet" : "slate"}>{member.role}</Badge>
                  )}
                </Td>
                <Td className="text-xs text-slate-400">{dateOnly(member.joined_at)}</Td>
                <Td>
                  {canManage && member.role !== "owner" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => removeMember(member.membership_id)}
                    >
                      Remove
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {canManage && invitations && invitations.length > 0 && (
        <Card title="Pending invitations">
          <Table headers={["E-mail", "Role", "Expires", ""]}>
            {invitations.map((invite) => (
              <tr key={invite.id}>
                <Td>{invite.email}</Td>
                <Td>
                  <Badge color="slate">{invite.role}</Badge>
                </Td>
                <Td className="text-xs text-slate-400">{dateOnly(invite.expires_at)}</Td>
                <Td>
                  <Button size="sm" variant="ghost" onClick={() => revokeInvite(invite.id)}>
                    Revoke
                  </Button>
                </Td>
              </tr>
            ))}
          </Table>
        </Card>
      )}

      {inviteOpen && (
        <InviteModal
          onClose={() => setInviteOpen(false)}
          onInvited={() => {
            setInviteOpen(false);
            invalidate();
          }}
        />
      )}
    </div>
  );
}

function InviteModal({ onClose, onInvited }: { onClose: () => void; onInvited: () => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("trader");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await api("/members/invitations", { method: "POST", body: { email, role } });
      toastSuccess("Invitation sent");
      onInvited();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to invite");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Invite team member">
      <div className="space-y-3">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <Field label="E-mail" required>
          <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <Field label="Role">
          <Select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="admin">Admin</option>
            <option value="trader">Trader</option>
            <option value="viewer">Viewer</option>
          </Select>
        </Field>
        <p className="text-xs text-slate-400">
          The invitee needs an Algo Matrics account registered with this e-mail address.
        </p>
        <Button className="w-full" onClick={submit} loading={submitting}>
          Send invitation
        </Button>
      </div>
    </Modal>
  );
}
