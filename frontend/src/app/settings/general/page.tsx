"use client";

import { useEffect, useState } from "react";

import { SectionCard } from "@/components/ui/section-card";
import { SettingsShell } from "@/components/settings/SettingsShell";
import { fetchDisplayTimeZone } from "@/lib/coachReadinessApi";
import { browserTimeZone } from "@/lib/formatInterviewTime";

export default function GeneralSettingsPage() {
  const [configured, setConfigured] = useState<string | null>(null);
  const [browserZone, setBrowserZone] = useState("UTC");

  useEffect(() => {
    setBrowserZone(browserTimeZone());
    void fetchDisplayTimeZone()
      .then(setConfigured)
      .catch(() => setConfigured(null));
  }, []);

  return (
    <SettingsShell
      activeHref="/settings/general"
      title="General"
      description="Workspace-wide display settings."
    >
      <SectionCard title="Time zone">
        <p className="m-0 text-sm text-[var(--text)]">
          {configured ? `Display timezone: ${configured}` : `This browser: ${browserZone}`}
        </p>
        <p className="mb-0 mt-1 text-sm text-[var(--text-dim)]">
          Interview times are stored as UTC and shown in this zone, with its abbreviation.
        </p>
      </SectionCard>
    </SettingsShell>
  );
}
