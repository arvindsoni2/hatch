"use client";

import { useState } from "react";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { acceptDebriefProposal, type DebriefProposal } from "@/lib/coachReadinessApi";

export interface DebriefProposalsProps {
  roundId: string;
  proposals: DebriefProposal[];
  onAccepted: (version: number, proposals: DebriefProposal[]) => void;
}

function pluralise(count: number, singular: string) {
  return `${count} new ${singular}${count === 1 ? "" : "s"}`;
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

  const dismiss = (proposal: DebriefProposal) =>
    setDismissed((current) => [...current, proposal.id]);

  return (
    <SectionCard
      title="Suggestions from this debrief"
      actions={
        <StatusBadge tone="success">
          <CheckCircle2 aria-hidden="true" className="h-3 w-3" />
          Saved
        </StatusBadge>
      }
    >
      <div className="space-y-2">
        {open.map((proposal) => (
          <div
            key={proposal.id}
            className="flex flex-col gap-2 rounded-[var(--radius-card)] bg-[var(--surface-2)] p-3"
          >
            {proposal.kind === "question_bank" ? (
              <>
                <span className="text-sm font-semibold text-[var(--text)]">
                  Add {pluralise(proposal.questions.length, "question")} to your Question Bank
                </span>
                {proposal.questions.map((text) => (
                  <span key={text} className="text-xs text-[var(--text-dim)]">
                    “{text}” is not in your bank yet.
                  </span>
                ))}
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void accept(proposal)}
                    loading={busy === proposal.id}
                  >
                    Add to Question Bank
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => dismiss(proposal)}
                  >
                    Not now
                  </Button>
                </div>
              </>
            ) : (
              <>
                <span className="text-sm font-semibold text-[var(--text)]">
                  Record that you used “{proposal.story_title ?? "a story"}”
                </span>
                <span className="text-xs text-[var(--text-dim)]">
                  Helps Hatch rank your stories for the next brief.
                </span>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void accept(proposal)}
                    loading={busy === proposal.id}
                  >
                    Record use
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => dismiss(proposal)}
                  >
                    Not now
                  </Button>
                </div>
              </>
            )}
          </div>
        ))}
        {error ? <p className="mb-0 text-sm text-[var(--danger)]" role="alert">{error}</p> : null}
      </div>
    </SectionCard>
  );
}
