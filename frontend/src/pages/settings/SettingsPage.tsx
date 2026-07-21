import { useNavigate, useParams } from "react-router";

import { PageHeader, Tabs } from "@/components/ui";
import { BrokersPage } from "@/pages/BrokersPage";
import { AppearanceSettings } from "@/pages/settings/AppearanceSettings";
import { ApiKeysSettings } from "@/pages/settings/ApiKeysSettings";
import { NotificationSettings } from "@/pages/settings/NotificationSettings";
import { OrganizationSettings } from "@/pages/settings/OrganizationSettings";
import { ProfileSettings } from "@/pages/settings/ProfileSettings";
import { SecuritySettings } from "@/pages/settings/SecuritySettings";
import { TeamSettings } from "@/pages/settings/TeamSettings";

const SECTIONS = [
  { key: "profile", label: "Profile" },
  { key: "brokers", label: "Brokers" },
  { key: "organization", label: "Organization" },
  { key: "team", label: "Team" },
  { key: "api-keys", label: "API Keys" },
  { key: "notifications", label: "Notifications" },
  { key: "appearance", label: "Appearance" },
  { key: "security", label: "Security" },
];

export function SettingsPage() {
  const { section = "profile" } = useParams();
  const navigate = useNavigate();

  return (
    <div>
      <PageHeader title="Settings" description="Manage your account, organization, and security" />
      <div className="mb-6">
        <Tabs tabs={SECTIONS} active={section} onChange={(key) => navigate(`/app/settings/${key}`)} />
      </div>
      {section === "profile" && <ProfileSettings />}
      {section === "brokers" && <BrokersPage embedded />}
      {section === "organization" && <OrganizationSettings />}
      {section === "team" && <TeamSettings />}
      {section === "api-keys" && <ApiKeysSettings />}
      {section === "notifications" && <NotificationSettings />}
      {section === "appearance" && <AppearanceSettings />}
      {section === "security" && <SecuritySettings />}
    </div>
  );
}
