import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button, Card, Field, Input, Select } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useProfile } from "@/lib/hooks";
import { useAuth } from "@/stores/auth";
import { toastError, toastSuccess } from "@/stores/toast";
import type { UserProfile } from "@/types/api";

const TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "America/New_York",
  "America/Chicago",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

export function ProfileSettings() {
  const { data: profile } = useProfile();
  const setUser = useAuth((state) => state.setUser);
  const client = useQueryClient();
  const [fullName, setFullName] = useState<string | null>(null);
  const [timezone, setTimezone] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [resent, setResent] = useState(false);

  if (!profile) return null;

  async function save() {
    setSaving(true);
    try {
      const updated = await api<UserProfile>("/users/me", {
        method: "PATCH",
        skipOrg: true,
        body: {
          full_name: fullName ?? profile!.full_name,
          timezone: timezone ?? profile!.timezone,
        },
      });
      setUser(updated);
      client.invalidateQueries({ queryKey: ["me"] });
      toastSuccess("Profile updated");
    } catch (error) {
      toastError("Update failed", error instanceof ApiError ? error.detail : undefined);
    } finally {
      setSaving(false);
    }
  }

  async function resendVerification() {
    await api("/auth/resend-verification", {
      method: "POST",
      skipAuth: true,
      body: { email: profile!.email },
    }).catch(() => undefined);
    setResent(true);
    toastSuccess("Verification e-mail sent");
  }

  async function uploadAvatar(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const updated = await api<UserProfile>("/users/me/avatar", {
        method: "POST",
        skipOrg: true,
        formData,
      });
      setUser(updated);
      client.invalidateQueries({ queryKey: ["me"] });
      toastSuccess("Avatar updated");
    } catch (error) {
      toastError("Upload failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <Card title="Profile">
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="flex size-14 items-center justify-center overflow-hidden rounded-full bg-accent-600 text-xl font-bold text-white">
              {profile.avatar_url ? (
                <img src={profile.avatar_url} alt="avatar" className="size-full object-cover" />
              ) : (
                profile.full_name.charAt(0).toUpperCase()
              )}
            </div>
            <div>
              <label className="cursor-pointer text-sm text-accent-500 hover:underline">
                Change avatar
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void uploadAvatar(file);
                  }}
                />
              </label>
              <p className="text-xs text-slate-400">PNG, JPEG, or WebP up to 2 MB</p>
            </div>
          </div>

          <Field label="Full name">
            <Input
              value={fullName ?? profile.full_name}
              onChange={(event) => setFullName(event.target.value)}
            />
          </Field>
          <Field label="E-mail">
            <div className="flex items-center gap-2">
              <Input value={profile.email} disabled />
              {profile.email_verified ? (
                <span className="text-xs text-profit-500">✓ Verified</span>
              ) : (
                <button
                  onClick={resendVerification}
                  disabled={resent}
                  className="shrink-0 text-xs text-accent-500 hover:underline disabled:opacity-50"
                >
                  {resent ? "Sent" : "Resend"}
                </button>
              )}
            </div>
          </Field>
          <Field label="Timezone">
            <Select
              value={timezone ?? profile.timezone}
              onChange={(event) => setTimezone(event.target.value)}
            >
              {TIMEZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </Select>
          </Field>
          <Button onClick={save} loading={saving}>
            Save changes
          </Button>
        </div>
      </Card>
    </div>
  );
}
