import { RemembersList } from "@/components/settings/RemembersList";
import { SettingsShell } from "@/components/settings/SettingsShell";

export default function RemembersPage() {
  return (
    <SettingsShell
      activeHref="/settings/privacy/remembers"
      title="Privacy"
      description="What Hatch remembers from Coach readiness, and how to delete it."
    >
      <RemembersList />
    </SettingsShell>
  );
}
