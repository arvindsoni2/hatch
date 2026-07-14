"use client";

import { SettingsShell } from "@/components/settings/SettingsShell";
import { AiCapabilitiesForm } from "@/components/setup/AiCapabilitiesForm";

export default function AiSettingsPage() {
  return (
    <SettingsShell
      activeHref="/settings/ai"
      title="AI & Capabilities"
      description="Choose local, cloud, or no AI independently from the Hatch capability profile. Provider secrets remain host-owned."
    >
      <AiCapabilitiesForm context="settings" />
    </SettingsShell>
  );
}
