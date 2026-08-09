import { Button } from "@/components/ui/button";
import type { ConversationCommandType, ConversationLiveView } from "@/lib/api";

interface ConversationControlsProps {
  live: ConversationLiveView;
  pending: boolean;
  textAnswer: string;
  onTextAnswerChange: (value: string) => void;
  onBeginText: () => void;
  onFinishText: () => void;
  onCommand: (command: ConversationCommandType) => void;
}

const SIMPLE_COMMANDS: ReadonlyArray<{
  command: ConversationCommandType;
  label: string;
}> = [
  { command: "start", label: "Start interview" },
  { command: "pause", label: "Pause interview" },
  { command: "resume", label: "Resume interview" },
  { command: "cancel_attempt", label: "Discard this answer" },
  { command: "retry_answer", label: "Try this question again" },
  { command: "retry_setup", label: "Retry interview setup" },
  { command: "retry_processing", label: "Retry answer processing" },
  { command: "skip_question", label: "Skip this question" },
];

export function ConversationControls({
  live,
  pending,
  textAnswer,
  onTextAnswerChange,
  onBeginText,
  onFinishText,
  onCommand,
}: ConversationControlsProps) {
  const allowed = new Set(live.allowed_commands);
  const isTypedDraft = live.conversation_state === "listening" && live.active_attempt?.recording_type === "text";
  const isAudioDraft = (live.conversation_state === "listening" || live.conversation_state === "paused")
    && live.active_attempt?.recording_type === "audio";

  return (
    <section aria-label="Interview controls" className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      {isTypedDraft ? (
        <div className="space-y-3">
          <label className="block text-sm font-semibold text-[var(--text)]" htmlFor="conversation-text-answer">
            Your answer
          </label>
          <textarea
            id="conversation-text-answer"
            value={textAnswer}
            onChange={(event) => onTextAnswerChange(event.target.value)}
            rows={7}
            disabled={pending}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          />
          {allowed.has("finish_answer") ? (
            <Button type="button" onClick={onFinishText} disabled={pending || textAnswer.trim().length === 0}>
              Submit written answer
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className={isTypedDraft ? "mt-4 flex flex-wrap gap-2" : "flex flex-wrap gap-2"}>
        {allowed.has("begin_answer") ? (
          <Button type="button" onClick={onBeginText} disabled={pending}>
            Answer in writing
          </Button>
        ) : null}
        {SIMPLE_COMMANDS.filter(({ command }) => (
          allowed.has(command)
          && !(isAudioDraft && ["pause", "resume", "cancel_attempt"].includes(command))
        )).map(({ command, label }) => (
          <Button
            key={command}
            type="button"
            variant="outline"
            onClick={() => onCommand(command)}
            disabled={pending}
          >
            {label}
          </Button>
        ))}
      </div>
    </section>
  );
}
