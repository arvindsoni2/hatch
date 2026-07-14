import type { AiMode } from "@/lib/setup";

export function AiEngineSelector({ value, onChange }: { value: AiMode; onChange: (mode: AiMode) => void }) {
  return (
    <fieldset>
      <legend aria-level={2} className="text-lg font-semibold text-[var(--text)]" role="heading">Choose an AI engine</legend>
      <p className="mt-1 text-sm text-[var(--text-muted)]">AI routing is independent from Hatch capabilities.</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {([
          ["none", "None", "Use Hatch without AI."],
          ["local", "Local", "Run selected models on this computer."],
          ["cloud", "Cloud", "Use provider-hosted models."],
        ] as const).map(([mode, label, description]) => (
          <label className="rounded-[var(--radius-control)] border border-[var(--border)] p-3" key={mode}>
            <span className="flex items-center gap-2 font-semibold text-[var(--text)]">
              <input aria-label={label} checked={value === mode} name="ai-engine" onChange={() => onChange(mode)} type="radio" />
              {label}
            </span>
            <span className="mt-1 block text-xs text-[var(--text-muted)]">{description}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
