"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { acceptDebriefProposal, type DebriefProposal } from "@/lib/coachReadinessApi";

export interface DebriefProposalsProps {
  roundId: string;
  proposals: DebriefProposal[];
  onAccepted: (version: number, proposals: DebriefProposal[]) => void;
}

export function DebriefProposals({ roundId, proposals, onAccepted }: DebriefProposalsProps) {
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const open = proposals.filter(
    (proposal) => !proposal.accepted && !dismissed.includes(proposal.id),
  );
  if (open.length === 0) return null;

  const accept = async (proposal: DebriefProposal) => {
    if (busy) return;
    setBusy(proposal.id);
    setError("");
    try {
      const read = await acceptDebriefProposal(roundId, proposal.id);
      onAccepted(read.version, read.proposals ?? []);
    } catch {
      setError("Could not apply that. Try again.");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <h3 className="m-0 text-sm font-semibold text-[var(--text)]">From this debrief</h3>
      <ul className="mt-2 space-y-2">
        {open.map((proposal) => (
          <li
            key={proposal.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-card)] bg-[var(--surface-2)] p-3"
          >
            <span className="text-sm text-[var(--text)]">
              {proposal.kind === "question_bank"
                ? `Add ${proposal.questions.length} new question${proposal.questions.length === 1 ? "" : "s"} to your Question Bank`
                : `Record that you used ${proposal.story_title ?? "a story"}`}
            </span>
            <span className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => void accept(proposal)}
                loading={busy === proposal.id}
              >
                Accept
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setDismissed((current) => [...current, proposal.id])}
              >
                Not now
              </Button>
            </span>
          </li>
        ))}
      </ul>
      {error ? <p className="mb-0 mt-2 text-sm text-[var(--danger)]" role="alert">{error}</p> : null}
    </div>
  );
}
