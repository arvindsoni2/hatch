import type { ConversationLiveView } from "@/lib/api";

export function ConversationProgress({ progress }: { progress: ConversationLiveView["progress"] }) {
  const current = progress.current_planned_position;
  return (
    <section aria-label="Interview progress" className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <h2 className="text-sm font-semibold text-[var(--text)]">Progress</h2>
      <p className="mt-2 text-sm text-[var(--text-muted)]">
        {progress.planned_questions_completed} of {progress.planned_questions_total} planned questions completed
      </p>
      {current === null ? null : (
        <p className="mt-1 text-xs text-[var(--text-muted)]">Current planned question: {current}</p>
      )}
      {progress.follow_ups_completed > 0 ? (
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {progress.follow_ups_completed} follow-up {progress.follow_ups_completed === 1 ? "question" : "questions"} completed
        </p>
      ) : null}
    </section>
  );
}
