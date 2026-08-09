"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  getCoachConversationLive,
  sendCoachConversationCommand,
  type ConversationCommandRequest,
  type ConversationCommandType,
  type ConversationLiveView,
} from "@/lib/api";
import { ConversationControls } from "./ConversationControls";
import { ConversationProgress } from "./ConversationProgress";
import { ConversationQuestion } from "./ConversationQuestion";
import { RetentionStatus } from "./RetentionStatus";

const PROCESSING_LABELS: Record<NonNullable<ConversationLiveView["processing"]["stage"]>, string> = {
  audio_persist: "Uploading answer",
  transcription: "Creating transcript",
  speech_analysis: "Reviewing answer",
  content_evaluation: "Reviewing answer",
  evidence_grounding: "Checking evidence",
  follow_up_decision: "Preparing next step",
  coaching_enrichment: "Preparing next step",
  audio_cleanup: "Preparing next step",
};

function stateLabel(live: ConversationLiveView): string {
  if (live.conversation_state === "processing_answer") {
    return live.processing.stage === null ? "Reviewing answer" : PROCESSING_LABELS[live.processing.stage];
  }
  const labels: Record<ConversationLiveView["conversation_state"], string> = {
    planning: "Preparing interview",
    ready: "Interview ready",
    asking: "Question ready",
    listening: "Answer in progress",
    processing_answer: "Reviewing answer",
    awaiting_next_action: "Answer review ready",
    coaching: "Coaching ready",
    asking_follow_up: "Preparing next step",
    advancing: "Preparing next step",
    paused: "Interview paused",
    reporting: "Preparing report",
    completed: "Interview complete",
    recoverable_error: "Interview needs attention",
    abandoned: "Interview ended",
    failed: "Interview could not continue",
  };
  return labels[live.conversation_state];
}

function isConflict(error: unknown): boolean {
  return error instanceof ApiError ? error.status === 409 : (
    typeof error === "object" && error !== null && "status" in error && error.status === 409
  );
}

type LiveRefreshResult =
  | { kind: "accepted"; live: ConversationLiveView }
  | { kind: "stale" }
  | { kind: "failed" };

export function ConversationSession({ sessionId }: { sessionId: string }) {
  const [live, setLive] = useState<ConversationLiveView | null>(null);
  const [pending, setPending] = useState(false);
  const [textAnswer, setTextAnswer] = useState("");
  const [announcement, setAnnouncement] = useState("Loading interview");
  const [loadError, setLoadError] = useState(false);
  const nextReadSequence = useRef(0);
  const acceptedReadSequence = useRef(0);
  const acceptedStateVersion = useRef(-1);

  const refreshLive = useCallback(async (announce = true): Promise<LiveRefreshResult> => {
    const readSequence = ++nextReadSequence.current;
    try {
      const current = await getCoachConversationLive(sessionId);
      if (readSequence < nextReadSequence.current || readSequence < acceptedReadSequence.current) {
        return { kind: "stale" };
      }
      if (current.state_version < acceptedStateVersion.current) {
        acceptedReadSequence.current = readSequence;
        setLive(null);
        setLoadError(true);
        setAnnouncement("We could not refresh this interview. Try again.");
        return { kind: "failed" };
      }
      acceptedReadSequence.current = readSequence;
      acceptedStateVersion.current = current.state_version;
      setLive(current);
      setLoadError(false);
      if (announce) setAnnouncement(stateLabel(current));
      return { kind: "accepted", live: current };
    } catch {
      if (readSequence < nextReadSequence.current || readSequence < acceptedReadSequence.current) {
        return { kind: "stale" };
      }
      acceptedReadSequence.current = readSequence;
      setLive(null);
      setLoadError(true);
      setAnnouncement("We could not refresh this interview. Try again.");
      return { kind: "failed" };
    }
  }, [sessionId]);

  useEffect(() => {
    void refreshLive();
  }, [refreshLive]);

  useEffect(() => {
    const handleFocus = () => {
      void refreshLive();
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refreshLive]);

  useEffect(() => {
    if (live?.conversation_state !== "processing_answer" && live?.conversation_state !== "reporting") {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshLive();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [live?.conversation_state, refreshLive]);

  const execute = useCallback(async (
    request: ConversationCommandRequest,
    options: { clearTextAfterRefresh?: boolean } = {},
  ) => {
    setPending(true);
    try {
      await sendCoachConversationCommand(sessionId, request);
      const refreshed = await refreshLive();
      if (refreshed.kind === "accepted" && options.clearTextAfterRefresh) setTextAnswer("");
    } catch (error) {
      if (isConflict(error)) {
        setLive(null);
        setLoadError(false);
        setAnnouncement("The interview changed on the server. Refreshing interview.");
        const refreshed = await refreshLive(false);
        if (refreshed.kind === "accepted") {
          setAnnouncement("The interview changed on the server. Your unsent answer is still here.");
        } else if (refreshed.kind === "failed") {
          setAnnouncement("The interview changed, but we could not refresh it. Your unsent answer is still here.");
        }
      } else {
        setAnnouncement("That action could not be completed. Your unsent answer is still here.");
      }
    } finally {
      setPending(false);
    }
  }, [refreshLive, sessionId]);

  const newEnvelope = useCallback(() => {
    if (live === null) return null;
    return {
      command_id: crypto.randomUUID(),
      expected_state_version: live.state_version,
      contract_version: "coach_conversation_command_v1" as const,
    };
  }, [live]);

  const beginText = useCallback(() => {
    const envelope = newEnvelope();
    if (envelope === null) return;
    void execute({
      ...envelope,
      command_type: "begin_answer",
      payload: { recording_type: "text", client_attempt_id: crypto.randomUUID() },
    });
  }, [execute, newEnvelope]);

  const finishText = useCallback(() => {
    const envelope = newEnvelope();
    const attemptId = live?.active_attempt?.id;
    const transcript = textAnswer.trim();
    if (envelope === null || attemptId === undefined || transcript.length === 0) return;
    void execute({
      ...envelope,
      command_type: "finish_answer",
      payload: { attempt_id: attemptId, transcript },
    }, { clearTextAfterRefresh: true });
  }, [execute, live?.active_attempt?.id, newEnvelope, textAnswer]);

  const executeSimpleCommand = useCallback((command: ConversationCommandType) => {
    const envelope = newEnvelope();
    if (envelope === null || live === null) return;
    const attemptId = live.active_attempt?.id;
    let request: ConversationCommandRequest | null = null;
    switch (command) {
      case "start":
      case "pause":
      case "resume":
      case "retry_setup":
      case "retry_processing":
      case "skip_question":
        request = { ...envelope, command_type: command, payload: {} } as ConversationCommandRequest;
        break;
      case "cancel_attempt":
        if (attemptId !== undefined) {
          request = { ...envelope, command_type: command, payload: { attempt_id: attemptId } } as ConversationCommandRequest;
        }
        break;
      case "retry_answer":
        request = {
          ...envelope,
          command_type: "retry_answer",
          payload: { question_id: live.active_question?.id ?? null },
        };
        break;
      default:
        break;
    }
    if (request !== null) void execute(request);
  }, [execute, live, newEnvelope]);

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <p aria-live="polite" className="mb-4 text-sm text-[var(--text-muted)]" role="status">
        {announcement}
      </p>

      {live === null ? (
        loadError ? (
          <button
            type="button"
            onClick={() => void refreshLive()}
            className="hatch-interactive rounded-[var(--radius-control)] border border-[var(--border)] px-4 py-2 text-sm font-semibold text-[var(--text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            Try refreshing interview
          </button>
        ) : null
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
          <div className="space-y-4">
            <ConversationQuestion live={live} />

            {live.conversation_state === "recoverable_error" && live.recoverable_error ? (
              <section className="rounded-xl border border-[var(--danger)] bg-[var(--surface)] p-4">
                <h2 className="text-sm font-semibold text-[var(--text)]">This interview needs attention</h2>
                <p className="mt-2 text-sm text-[var(--text-muted)]">{live.recoverable_error.message}</p>
              </section>
            ) : null}

            {live.conversation_state === "completed" || live.conversation_state === "abandoned" || live.conversation_state === "failed" ? (
              <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
                <h2 className="text-base font-semibold text-[var(--text)]">{stateLabel(live)}</h2>
                <p className="mt-2 text-sm text-[var(--text-muted)]">This interview is read-only.</p>
              </section>
            ) : (
              <ConversationControls
                live={live}
                pending={pending}
                textAnswer={textAnswer}
                onTextAnswerChange={setTextAnswer}
                onBeginText={beginText}
                onFinishText={finishText}
                onCommand={executeSimpleCommand}
              />
            )}
          </div>

          <aside className="space-y-4">
            <ConversationProgress progress={live.progress} />
            <RetentionStatus retention={live.retention} />
          </aside>
        </div>
      )}
    </main>
  );
}
