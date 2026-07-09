import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button, Card, Field, Input, Select, SkeletonRows, Switch } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  useNotificationPreferences,
  useProfile,
  useUpdateNotificationPreferences,
} from "@/lib/hooks";
import { useAuth } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";
import type { NotificationPreference, UserProfile } from "@/types/api";

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
    <div className="max-w-xl space-y-6">
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
      <DeliveryChannels />
    </div>
  );
}

const CHANNEL_LABELS: Record<string, string> = {
  email: "E-mail",
  webhook: "Webhook",
};

function hasChannel(pref: NotificationPreference, channel: string): boolean {
  return pref.enabled_channels.includes(channel);
}

function withChannel(
  pref: NotificationPreference,
  channel: string,
  on: boolean,
): string[] {
  const set = new Set(pref.enabled_channels);
  if (on) set.add(channel);
  else set.delete(channel);
  set.add("in_app"); // in-app is always available
  return Array.from(set);
}

function DeliveryChannels() {
  const { data } = useNotificationPreferences();
  const update = useUpdateNotificationPreferences();
  const [edits, setEdits] = useState<Partial<NotificationPreference>>({});

  if (!data) return <Card title="Delivery channels"><SkeletonRows rows={4} cols={2} /></Card>;

  const draft: NotificationPreference = { ...data, ...edits };

  const patch = (next: Partial<NotificationPreference>) =>
    setEdits((prev) => ({ ...prev, ...next }));

  async function save() {
    try {
      await update.mutateAsync(draft);
      setEdits({});
      toastSuccess("Delivery channels saved");
    } catch (error) {
      toastError("Save failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <Card title="Delivery channels">
      <div className="space-y-4">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Choose how alerts reach you beyond the in-app bell.
        </p>
        {["email", "webhook"].map((channel) => (
          <div
            key={channel}
            className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2.5 dark:border-surface-700"
          >
            <span className="text-sm">{CHANNEL_LABELS[channel]}</span>
            <Switch
              checked={hasChannel(draft, channel)}
              onChange={(on) => patch({ enabled_channels: withChannel(draft, channel, on) })}
            />
          </div>
        ))}

        {hasChannel(draft, "webhook") && (
          <Field label="Webhook URL" hint="Must be an https:// endpoint.">
            <Input
              type="url"
              placeholder="https://example.com/hooks/alerts"
              value={draft.webhook_url ?? ""}
              onChange={(e) => patch({ webhook_url: e.target.value || null })}
            />
          </Field>
        )}

        <Field label="Minimum severity" hint="Only send email/webhook at or above this level.">
          <Select
            value={draft.min_severity}
            onChange={(e) =>
              patch({ min_severity: e.target.value as NotificationPreference["min_severity"] })
            }
          >
            <option value="info">Info</option>
            <option value="success">Success</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
          </Select>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Quiet hours start">
            <Input
              type="time"
              value={draft.quiet_start ?? ""}
              onChange={(e) => patch({ quiet_start: e.target.value || null })}
            />
          </Field>
          <Field label="Quiet hours end">
            <Input
              type="time"
              value={draft.quiet_end ?? ""}
              onChange={(e) => patch({ quiet_end: e.target.value || null })}
            />
          </Field>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2.5 dark:border-surface-700">
          <span className="text-sm">Critical alerts ignore quiet hours</span>
          <Switch
            checked={draft.critical_overrides_quiet}
            onChange={(on) => patch({ critical_overrides_quiet: on })}
          />
        </div>

        <Button onClick={save} loading={update.isPending}>
          Save delivery channels
        </Button>
      </div>
    </Card>
  );
}
