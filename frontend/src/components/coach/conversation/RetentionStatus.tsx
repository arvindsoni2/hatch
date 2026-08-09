import type { ConversationLiveView } from "@/lib/api";

const AUDIO_POLICY_LABELS: Record<ConversationLiveView["retention"]["audio_policy"], string> = {
  delete_after_processing: "Delete audio after processing",
  retain_until_deleted: "Keep audio until you delete it",
};

const AUDIO_STATE_LABELS: Record<NonNullable<ConversationLiveView["retention"]["current_audio_state"]>, string> = {
  not_applicable: "No audio for this answer",
  temporary: "Audio is temporarily retained",
  retained: "Audio is retained",
  delete_pending: "Audio deletion is pending",
  deleted: "Audio has been deleted",
  delete_failed: "Audio deletion needs another attempt",
};

export function RetentionStatus({ retention }: { retention: ConversationLiveView["retention"] }) {
  return (
    <section aria-label="Audio privacy" className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <h2 className="text-sm font-semibold text-[var(--text)]">Audio privacy</h2>
      <p className="mt-2 text-sm text-[var(--text-muted)]">
        {AUDIO_POLICY_LABELS[retention.audio_policy]}
      </p>
      {retention.current_audio_state === null ? null : (
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {AUDIO_STATE_LABELS[retention.current_audio_state]}
        </p>
      )}
    </section>
  );
}
