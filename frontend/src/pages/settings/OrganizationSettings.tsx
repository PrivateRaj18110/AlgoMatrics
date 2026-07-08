import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button, Card, Field, Input, Switch } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { activeOrg, useAuth } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";

export function OrganizationSettings() {
  const org = activeOrg();
  const loadContext = useAuth((state) => state.loadContext);
  const client = useQueryClient();
  const [name, setName] = useState<string | null>(null);
  const [liveTrading, setLiveTrading] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);

  if (!org) return null;

  const canManage = org.role === "owner" || org.role === "admin";
  const currentLive = Boolean(org.settings.live_trading_enabled);

  async function save() {
    setSaving(true);
    try {
      await api("/organizations/current", {
        method: "PATCH",
        body: {
          name: name ?? org!.name,
          settings: { live_trading_enabled: liveTrading ?? currentLive },
        },
      });
      await loadContext();
      client.invalidateQueries();
      toastSuccess("Organization updated");
    } catch (error) {
      toastError("Update failed", error instanceof ApiError ? error.detail : undefined);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-xl">
      <Card title="Organization">
        <div className="space-y-4">
          <Field label="Name">
            <Input
              value={name ?? org.name}
              disabled={!canManage}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label="Slug">
            <Input value={org.slug} disabled />
          </Field>
          <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3 dark:border-surface-700">
            <div>
              <p className="text-sm font-medium">Live trading enabled</p>
              <p className="text-xs text-slate-400">
                Organization-level guard on top of plan entitlements
              </p>
            </div>
            <Switch
              checked={liveTrading ?? currentLive}
              onChange={setLiveTrading}
              disabled={!canManage}
            />
          </div>
          {canManage ? (
            <Button onClick={save} loading={saving}>
              Save changes
            </Button>
          ) : (
            <p className="text-sm text-slate-400">
              You need the owner or admin role to change organization settings.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
