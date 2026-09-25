"use client";

import { Button } from "@/components/ui/button";

interface PrivacyControlsProps {
  canDeleteTranscript: boolean;
  canDeleteSession: boolean;
  pending?: boolean;
  onDeleteTranscript: () => void;
  onDeleteSession: () => void;
  statusMessage?: string | null;
  errorMessage?: string | null;
}

export function PrivacyControls({
  canDeleteTranscript,
  canDeleteSession,
  pending = false,
  onDeleteTranscript,
  onDeleteSession,
  statusMessage = null,
  errorMessage = null,
}: PrivacyControlsProps) {
  return (
    <section aria-labelledby="privacy-controls-title" className="space-y-4 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
      <div>
        <h2 id="privacy-controls-title" className="text-lg font-semibold text-[var(--text)]">Privacy controls</h2>
        <p className="mt-1 text-sm leading-6 text-[var(--text-muted)]">Delete answer transcripts or remove the full interview. Deletion cannot be undone.</p>
      </div>
      <div className="flex flex-wrap gap-3">
        {canDeleteTranscript ? <Button type="button" variant="outline" disabled={pending} onClick={onDeleteTranscript}>Delete transcript</Button> : null}
        {canDeleteSession ? <Button type="button" variant="destructive" disabled={pending} onClick={onDeleteSession}>Delete interview</Button> : null}
      </div>
      {statusMessage ? <p role="status" className="text-sm text-[var(--text-muted)]">{statusMessage}</p> : null}
      {errorMessage ? <p role="alert" className="text-sm text-[var(--danger)]">{errorMessage}</p> : null}
    </section>
  );
}
