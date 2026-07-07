"use client";

import { RotateCcw, Save } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SettingsSaveBarProps {
  dirty: boolean;
  saving: boolean;
  saveLabel: string;
  onDiscard: () => void;
  onSave: () => void;
}

export function SettingsSaveBar({
  dirty,
  saving,
  saveLabel,
  onDiscard,
  onSave,
}: SettingsSaveBarProps) {
  if (!dirty) return null;

  return (
    <div
      className="sticky bottom-20 z-20 flex flex-col gap-3 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-3 shadow-lg md:bottom-4 md:flex-row md:items-center md:justify-between"
      role="status"
    >
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-dim)]">
        <span className="h-2 w-2 rounded-full bg-[var(--warning)]" aria-hidden="true" />
        Unsaved changes
      </div>
      <div className="grid grid-cols-2 gap-2 sm:flex">
        <Button type="button" variant="outline" onClick={onDiscard} disabled={saving}>
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Discard
        </Button>
        <Button type="button" onClick={onSave} loading={saving}>
          <Save className="h-4 w-4" aria-hidden="true" />
          {saveLabel}
        </Button>
      </div>
    </div>
  );
}
