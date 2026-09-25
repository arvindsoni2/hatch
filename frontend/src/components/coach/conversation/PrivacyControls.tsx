"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

type ConfirmationTarget = "transcript" | "session" | null;

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
  const [confirmationTarget, setConfirmationTarget] = useState<ConfirmationTarget>(null);
  const isSessionDeletion = confirmationTarget === "session";

  const confirmDeletion = () => {
    if (isSessionDeletion) onDeleteSession();
    else if (confirmationTarget === "transcript") onDeleteTranscript();
    setConfirmationTarget(null);
  };

  return (
    <section aria-labelledby="privacy-controls-title" className="space-y-4 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
      <div>
        <h2 id="privacy-controls-title" className="text-lg font-semibold text-[var(--text)]">Privacy controls</h2>
        <p className="mt-1 text-sm leading-6 text-[var(--text-muted)]">Delete answer transcripts or remove the full interview. Deletion cannot be undone.</p>
      </div>
      <div className="flex flex-wrap gap-3">
        {canDeleteTranscript ? <Button type="button" variant="outline" disabled={pending} onClick={() => setConfirmationTarget("transcript")}>Delete transcript</Button> : null}
        {canDeleteSession ? <Button type="button" variant="destructive" disabled={pending} onClick={() => setConfirmationTarget("session")}>Delete interview</Button> : null}
      </div>
      {confirmationTarget !== null ? (
        <div
          aria-labelledby="privacy-confirmation-title"
          aria-modal="true"
          className="space-y-3 rounded-lg border border-[var(--danger)] bg-[var(--surface-2)] p-4"
          role="alertdialog"
        >
          <h3 id="privacy-confirmation-title" className="text-sm font-semibold text-[var(--text)]">
            {isSessionDeletion ? "Confirm interview deletion" : "Confirm transcript deletion"}
          </h3>
          <p className="text-sm leading-6 text-[var(--text-muted)]">
            {isSessionDeletion
              ? "This removes the interview and its retained data. This cannot be undone."
              : "This removes the selected answer transcript. This cannot be undone."}
          </p>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="destructive" onClick={confirmDeletion}>
              {isSessionDeletion ? "Confirm interview deletion" : "Confirm transcript deletion"}
            </Button>
            <Button type="button" variant="outline" onClick={() => setConfirmationTarget(null)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
      {statusMessage ? <p role="status" className="text-sm text-[var(--text-muted)]">{statusMessage}</p> : null}
      {errorMessage ? <p role="alert" className="text-sm text-[var(--danger)]">{errorMessage}</p> : null}
    </section>
  );
}
