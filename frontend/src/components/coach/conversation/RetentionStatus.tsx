import { Button } from "@/components/ui/button";
import type { ConversationLiveView } from "@/lib/api";

const FUTURE_AUDIO_POLICY_LABELS: Record<ConversationLiveView["retention"]["audio_policy"], string> = {
  delete_after_processing: "Delete audio after processing",
  retain_until_deleted: "Keep audio until I delete it",
};

const AUDIO_STATE_LABELS: Record<NonNullable<ConversationLiveView["retention"]["current_audio_state"]>, string> = {
  not_applicable: "No audio was recorded for this answer.",
  temporary: "Audio is temporarily retained until processing cleanup can run.",
  retained: "Audio is retained for this answer.",
  delete_pending: "Audio deletion is in progress.",
  deleted: "Audio has been deleted. Your transcript, answer review, and saved delivery observations remain available.",
  delete_failed: "Audio could not be deleted. You can try again.",
};

interface RetentionStatusProps {
  live: ConversationLiveView;
  pending: boolean;
  onUpdatePolicy: (policy: ConversationLiveView["retention"]["audio_policy"]) => void;
  onDeleteAudio: (attemptId: string) => void;
}

export function RetentionStatus({ live, pending, onUpdatePolicy, onDeleteAudio }: RetentionStatusProps) {
  const activeAttempt = live.active_attempt;
  const retryableAudioCleanupAttemptId = live.retention.retryable_audio_cleanup_attempt_id;
  const canRetryCancelledAudioCleanup = retryableAudioCleanupAttemptId !== null
    && live.allowed_commands.includes("delete_audio");
  const snapshotPolicy = activeAttempt?.audio_retention_policy;
  const futurePolicyTarget = live.retention.audio_policy === "retain_until_deleted"
    ? "delete_after_processing"
    : "retain_until_deleted";
  const futurePolicyAction = futurePolicyTarget === "delete_after_processing"
    ? "Delete audio after processing for future answers"
    : "Keep audio for future answers until I delete it";

  return (
    <section aria-label="Audio privacy" className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <h2 className="text-sm font-semibold text-[var(--text)]">Audio privacy</h2>
      <div className="mt-3">
        <h3 className="text-sm font-semibold text-[var(--text)]">Future answers</h3>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          {FUTURE_AUDIO_POLICY_LABELS[live.retention.audio_policy]}
        </p>
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          Changes apply only to future answers. They cannot restore deleted audio or remove audio retained for an earlier answer.
        </p>
        {live.allowed_commands.includes("update_retention") ? (
          <Button
            type="button"
            variant="outline"
            className="mt-3"
            disabled={pending}
            onClick={() => onUpdatePolicy(futurePolicyTarget)}
          >
            {futurePolicyAction}
          </Button>
        ) : null}
      </div>
      <div className="mt-4">
        <h3 className="text-sm font-semibold text-[var(--text)]">This answer</h3>
        {canRetryCancelledAudioCleanup ? (
          <>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              A cancelled recording could not be deleted. You can try again.
            </p>
            <Button
              type="button"
              variant="outline"
              className="mt-3"
              disabled={pending}
              onClick={() => onDeleteAudio(retryableAudioCleanupAttemptId)}
            >
              Retry audio deletion
            </Button>
          </>
        ) : null}
        {snapshotPolicy === null || snapshotPolicy === undefined ? null : (
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            {FUTURE_AUDIO_POLICY_LABELS[snapshotPolicy]}
          </p>
        )}
        {live.retention.current_audio_state === null ? null : (
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            {AUDIO_STATE_LABELS[live.retention.current_audio_state]}
          </p>
        )}
        {live.allowed_commands.includes("delete_audio") && activeAttempt !== null ? (
          <Button
            type="button"
            variant="outline"
            className="mt-3"
            disabled={pending}
            onClick={() => onDeleteAudio(activeAttempt.id)}
          >
            Delete audio for this answer
          </Button>
        ) : null}
      </div>
    </section>
  );
}
