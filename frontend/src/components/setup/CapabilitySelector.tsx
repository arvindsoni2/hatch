import { useState } from "react";
import type { BackendProfile } from "@/lib/setup";
import { profileLabel } from "@/lib/setup";

export function CapabilitySelector({ value, onChange }: { value: BackendProfile; onChange: (profile: BackendProfile) => void }) {
  const [advanced, setAdvanced] = useState(value !== "core");
  const profiles: BackendProfile[] = ["browser", "local-embeddings", "full"];
  return (
    <fieldset>
      <legend className="text-lg font-semibold text-[var(--text)]">Choose Hatch capabilities</legend>
      <label className="mt-3 flex items-center gap-2 rounded-[var(--radius-control)] border border-[var(--border)] p-3 font-semibold text-[var(--text)]">
        <input checked={value === "core"} name="capability-profile" onChange={() => onChange("core")} type="radio" />
        Standard Hatch
      </label>
      <button className="mt-3 text-sm font-semibold text-[var(--accent)]" onClick={() => setAdvanced((open) => !open)} type="button">
        Advanced capabilities
      </button>
      {advanced ? (
        <div className="mt-3 grid gap-2">
          {profiles.map((profile) => (
            <label className="flex items-center gap-2 rounded-[var(--radius-control)] border border-[var(--border)] p-3 text-sm text-[var(--text)]" key={profile}>
              <input checked={value === profile} name="capability-profile" onChange={() => onChange(profile)} type="radio" />
              {profileLabel(profile)}
            </label>
          ))}
        </div>
      ) : null}
    </fieldset>
  );
}
