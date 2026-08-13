import { Button } from "@/components/ui/button";
import type {
  ConversationAttemptHistoryRead,
  ConversationCommandType,
  ConversationReviewLevel,
} from "@/lib/api";
import type { ReviewCommandHandler } from "./AnswerReview";

const LEVEL_LABELS: Record<ConversationReviewLevel, string> = {
  needs_work: "Needs work",
  developing: "Developing",
  interview_ready: "Interview-ready",
  strong: "Strong",
  not_assessed: "Not assessed",
};

const AUDIO_LABELS = {
  not_applicable: "No audio",
  temporary: "Audio temporary",
  retained: "Audio retained",
  delete_pending: "Audio deletion pending",
  deleted: "Audio deleted",
  delete_failed: "Audio deletion failed",
} as const;

interface AttemptHistoryProps {
  attempts: ReadonlyArray<ConversationAttemptHistoryRead>;
  allowedCommands: ReadonlyArray<ConversationCommandType>;
  pending: boolean;
  onCommand: ReviewCommandHandler;
}

export function AttemptHistory({ attempts, allowedCommands, pending, onCommand }: AttemptHistoryProps) {
  const canAccept = allowedCommands.includes("accept_attempt");

  if (attempts.length === 0) return null;

  return (
    <section aria-label="Attempt history" className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <h2 className="text-base font-semibold text-[var(--text)]">Attempt history</h2>
      <div className="mt-3 space-y-2">
        {attempts.map((attempt) => (
          <details key={attempt.attempt_id} className="rounded-lg bg-[var(--surface-2)] p-3">
            <summary className="cursor-pointer text-sm font-semibold text-[var(--text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]">
              <span>
                Attempt {attempt.attempt_number} - {LEVEL_LABELS[attempt.answer_level]} - {attempt.accepted ? "accepted" : "not accepted"}
              </span>
              {attempt.audio_state === null ? null : (
                <span className="mt-1 block text-xs font-normal text-[var(--text-muted)]">
                  {AUDIO_LABELS[attempt.audio_state]}
                </span>
              )}
            </summary>
            <div className="mt-3 space-y-2">
              <p className="text-sm text-[var(--text-muted)]">
                {attempt.transcript_available ? "Transcript available" : "Transcript unavailable"}
              </p>
              {canAccept && !attempt.accepted ? (
                <Button
                  type="button"
                  disabled={pending}
                  onClick={() => onCommand("accept_attempt", { attempt_id: attempt.attempt_id })}
                >
                  Accept attempt {attempt.attempt_number}
                </Button>
              ) : null}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
