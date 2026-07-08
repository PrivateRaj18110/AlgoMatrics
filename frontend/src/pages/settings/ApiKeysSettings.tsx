import { useQueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
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
  Switch,
  Table,
  Td,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { dateOnly, dateTime } from "@/lib/format";
import { useAuth } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";
import type { ApiKey, CreatedApiKey } from "@/types/api";

function useApiKeys() {
  const orgId = useAuth((state) => state.activeOrgId);
  return useQuery({
    queryKey: ["api-keys", orgId],
    queryFn: () => api<ApiKey[]>("/api-keys"),
  });
}

export function ApiKeysSettings() {
  const { data: keys, isLoading } = useApiKeys();
  const [createOpen, setCreateOpen] = useState(false);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const client = useQueryClient();

  async function revoke(id: string) {
    try {
      await api(`/api-keys/${id}`, { method: "DELETE" });
      client.invalidateQueries({ queryKey: ["api-keys"] });
      toastSuccess("API key revoked");
    } catch (error) {
      toastError("Revoke failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <div className="max-w-3xl">
      <Card
        title="API keys"
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            Create key
          </Button>
        }
      >
        {isLoading ? (
          <SkeletonRows rows={3} cols={4} />
        ) : !keys || keys.length === 0 ? (
          <EmptyState
            title="No API keys"
            body="Create an API key to access the platform programmatically."
          />
        ) : (
          <Table headers={["Name", "Prefix", "Scopes", "Last used", "Status", ""]}>
            {keys.map((key) => (
              <tr key={key.id}>
                <Td className="font-medium">{key.name}</Td>
                <Td className="font-mono text-xs">{key.prefix}…</Td>
                <Td>
                  <div className="flex gap-1">
                    {key.scopes.map((scope) => (
                      <Badge key={scope} color="blue">
                        {scope}
                      </Badge>
                    ))}
                  </div>
                </Td>
                <Td className="text-xs text-slate-400">
                  {key.last_used_at ? dateTime(key.last_used_at) : "Never"}
                </Td>
                <Td>
                  {key.revoked_at ? (
                    <Badge color="red">revoked</Badge>
                  ) : key.expires_at && new Date(key.expires_at) < new Date() ? (
                    <Badge color="amber">expired</Badge>
                  ) : (
                    <Badge color="green">active</Badge>
                  )}
                </Td>
                <Td>
                  {!key.revoked_at && (
                    <Button size="sm" variant="ghost" onClick={() => revoke(key.id)}>
                      Revoke
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {createOpen && (
        <CreateKeyModal
          onClose={() => setCreateOpen(false)}
          onCreated={(result) => {
            setCreateOpen(false);
            setCreated(result);
            client.invalidateQueries({ queryKey: ["api-keys"] });
          }}
        />
      )}

      {created && (
        <Modal open onClose={() => setCreated(null)} title="API key created">
          <div className="space-y-3">
            <p className="text-sm text-slate-500">
              Copy this secret now — it will not be shown again.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 overflow-x-auto rounded-lg bg-slate-100 px-3 py-2 font-mono text-xs dark:bg-surface-800">
                {created.secret}
              </code>
              <Button
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(created.secret);
                  toastSuccess("Copied to clipboard");
                }}
              >
                Copy
              </Button>
            </div>
            <p className="text-xs text-slate-400">
              Expires: {created.key.expires_at ? dateOnly(created.key.expires_at) : "never"}
            </p>
          </div>
        </Modal>
      )}
    </div>
  );
}

function CreateKeyModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (result: CreatedApiKey) => void;
}) {
  const [name, setName] = useState("");
  const [tradeScope, setTradeScope] = useState(false);
  const [expiryDays, setExpiryDays] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const scopes = tradeScope ? ["read", "trade"] : ["read"];
      const result = await api<CreatedApiKey>("/api-keys", {
        method: "POST",
        body: {
          name,
          scopes,
          expires_in_days: expiryDays ? Number(expiryDays) : null,
        },
      });
      toastSuccess("API key created");
      onCreated(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Create API key">
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <Field label="Name" required>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="CI bot" />
        </Field>
        <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3 dark:border-surface-700">
          <div>
            <p className="text-sm font-medium">Trading scope</p>
            <p className="text-xs text-slate-400">Allow placing orders (not just read access)</p>
          </div>
          <Switch checked={tradeScope} onChange={setTradeScope} />
        </div>
        <Field label="Expiry (days)" hint="Leave blank for no expiry">
          <Input
            type="number"
            value={expiryDays}
            onChange={(event) => setExpiryDays(event.target.value)}
            placeholder="90"
          />
        </Field>
        <Button className="w-full" onClick={submit} loading={submitting}>
          Create key
        </Button>
      </div>
    </Modal>
  );
}
