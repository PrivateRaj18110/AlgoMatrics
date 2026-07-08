import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button, Card, SkeletonRows, Switch } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useProfile } from "@/lib/hooks";
import { useAuth } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";
import type { UserProfile } from "@/types/api";

const LABELS: Record<string, string> = {
  email_order_fills: "E-mail: order fills",
  email_risk_alerts: "E-mail: risk alerts",
  email_billing: "E-mail: billing",
  email_strategy_status: "E-mail: strategy status",
  inapp_order_fills: "In-app: order fills",
  inapp_risk_alerts: "In-app: risk alerts",
  inapp_billing: "In-app: billing",
  inapp_strategy_status: "In-app: strategy status",
};

export function NotificationSettings() {
  const { data: profile } = useProfile();
  const setUser = useAuth((state) => state.setUser);
  const client = useQueryClient();
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  if (!profile) return <Card><SkeletonRows rows={4} cols={2} /></Card>;

  const settings = { ...profile.notification_settings, ...overrides };

  async function save() {
    setSaving(true);
    try {
      const updated = await api<UserProfile>("/users/me/notifications", {
        method: "PUT",
        skipOrg: true,
        body: { settings },
      });
      setUser(updated);
      setOverrides({});
      client.invalidateQueries({ queryKey: ["me"] });
      toastSuccess("Notification preferences saved");
    } catch (error) {
      toastError("Save failed", error instanceof ApiError ? error.detail : undefined);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-xl">
      <Card title="Notification preferences">
        <div className="space-y-3">
          {Object.entries(settings).map(([key, value]) => (
            <div
              key={key}
              className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2.5 dark:border-surface-700"
            >
              <span className="text-sm">{LABELS[key] ?? key}</span>
              <Switch
                checked={value}
                onChange={(next) => setOverrides((prev) => ({ ...prev, [key]: next }))}
              />
            </div>
          ))}
          <Button onClick={save} loading={saving}>
            Save preferences
          </Button>
        </div>
      </Card>
    </div>
  );
}
