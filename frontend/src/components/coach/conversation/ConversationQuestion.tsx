import type { ConversationLiveView } from "@/lib/api";

function currentMode(state: ConversationLiveView["conversation_state"]): string {
  if (state === "awaiting_next_action") return "Review";
  if (state === "coaching") return "Coaching";
  return "Interview";
}

export function ConversationQuestion({ live }: { live: ConversationLiveView }) {
  const question = live.active_question;
  const transcript = live.active_attempt?.transcript_version?.transcript;

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-[var(--text-muted)]">
          {currentMode(live.conversation_state)}
        </p>
        {question?.question_kind === "adaptive_follow_up" ? (
          <span className="rounded-full border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-muted)]">
            Follow-up question
          </span>
        ) : null}
      </div>

      {question ? (
        <>
          <h1 className="text-xl font-semibold leading-relaxed text-[var(--text)]">
            {question.text}
          </h1>
          <p className="mt-2 text-sm text-[var(--text-muted)]">
            {question.attempts_remaining} of {question.attempt_limit} attempts available
          </p>
        </>
      ) : (
        <p className="text-sm text-[var(--text-muted)]">No current question is available.</p>
      )}

      {transcript ? (
        <div className="mt-5 border-t border-[var(--border)] pt-4">
          <h2 className="text-sm font-semibold text-[var(--text)]">Your transcript</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-muted)]">
            {transcript}
          </p>
        </div>
      ) : null}
    </section>
  );
}
