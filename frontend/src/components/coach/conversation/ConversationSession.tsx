"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  getCoachConversationLive,
  sendCoachConversationCommand,
  type ConversationCommandRequest,
  type ConversationCommandResult,
  type ConversationCommandType,
  type ConversationLiveView,
} from "@/lib/api";
import { ConversationControls } from "./ConversationControls";
import { ConversationProgress } from "./ConversationProgress";
import { ConversationQuestion } from "./ConversationQuestion";
import {
  ConversationRecorder,
  type RecorderCancelOutcome,
  type RecorderTransitionOutcome,
} from "./ConversationRecorder";
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
  | { kind: "accepted"; live: ConversationLiveView; readSequence: number }
  | { kind: "stale"; readSequence: number }
  | { kind: "failed"; readSequence: number };

type CommandExecutionResult = {
  post:
    | { kind: "accepted"; result: ConversationCommandResult }
    | { kind: "rejected" };
  refresh: LiveRefreshResult | null;
};

type RecorderCommandAuthority = {
  state: ConversationCommandResult["state"];
  stateVersion: number;
  attemptId: string | null;
  resumed: boolean;
};

type RecorderAuthorityResult =
  | { kind: "accepted"; authority: RecorderCommandAuthority }
  | { kind: "rejected" };

const ACCEPTED_COMMAND_RESULTS = new Set<ConversationCommandResult["result"]>([
  "completed", "accepted_processing", "duplicate",
]);

export function ConversationSession({ sessionId }: { sessionId: string }) {
  const [live, setLive] = useState<ConversationLiveView | null>(null);
  const [pending, setPending] = useState(false);
  const [textAnswer, setTextAnswer] = useState("");
  const [announcement, setAnnouncement] = useState("Loading interview");
  const [loadError, setLoadError] = useState(false);
  const nextReadSequence = useRef(0);
  const acceptedReadSequence = useRef(0);
  const acceptedStateVersion = useRef(-1);
  const lastRecorderAuthority = useRef<ConversationLiveView | null>(null);
  const latestAuthority = useRef<ConversationLiveView | null>(null);
  const pendingAuthorityReads = useRef(new Map<number, Promise<LiveRefreshResult>>());

  const refreshLive = useCallback((announce = true): Promise<LiveRefreshResult> => {
    const readSequence = ++nextReadSequence.current;
    const read = (async (): Promise<LiveRefreshResult> => {
      try {
        const current = await getCoachConversationLive(sessionId);
        if (
          current.state_version < acceptedStateVersion.current
          || (
            current.state_version === acceptedStateVersion.current
            && readSequence < acceptedReadSequence.current
          )
        ) {
          return { kind: "stale", readSequence };
        }
        acceptedReadSequence.current = readSequence;
        acceptedStateVersion.current = current.state_version;
        lastRecorderAuthority.current = current;
        latestAuthority.current = current;
        setLive(current);
        setLoadError(false);
        if (announce) setAnnouncement(stateLabel(current));
        return { kind: "accepted", live: current, readSequence };
      } catch {
        if (readSequence < nextReadSequence.current || readSequence < acceptedReadSequence.current) {
          return { kind: "stale", readSequence };
        }
        acceptedReadSequence.current = readSequence;
        latestAuthority.current = null;
        setLive(null);
        setLoadError(true);
        setAnnouncement("We could not refresh this interview. Try again.");
        return { kind: "failed", readSequence };
      }
    })();
    pendingAuthorityReads.current.set(readSequence, read);
    void read.finally(() => {
      if (pendingAuthorityReads.current.get(readSequence) === read) {
        pendingAuthorityReads.current.delete(readSequence);
      }
    });
    return read;
  }, [sessionId]);

  const waitForLatestAuthority = useCallback(async (
    completedReadSequence: number,
  ): Promise<ConversationLiveView | null> => {
    while (true) {
      const latestReadSequence = nextReadSequence.current;
      if (latestReadSequence <= completedReadSequence) return latestAuthority.current;
      const pendingRead = pendingAuthorityReads.current.get(latestReadSequence);
      if (pendingRead !== undefined) await pendingRead;
      if (latestReadSequence === nextReadSequence.current) return latestAuthority.current;
    }
  }, []);

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
  ): Promise<CommandExecutionResult> => {
    setPending(true);
    try {
      const commandResult = await sendCoachConversationCommand(sessionId, request);
      const refreshed = await refreshLive();
      const accepted = ACCEPTED_COMMAND_RESULTS.has(commandResult.result);
      if (accepted && refreshed.kind === "accepted" && options.clearTextAfterRefresh) setTextAnswer("");
      return {
        post: accepted ? { kind: "accepted", result: commandResult } : { kind: "rejected" },
        refresh: refreshed,
      };
    } catch (error) {
      if (isConflict(error)) {
        latestAuthority.current = null;
        setLive(null);
        setLoadError(false);
        setAnnouncement("The interview changed on the server. Refreshing interview.");
        const refreshed = await refreshLive(false);
        if (refreshed.kind === "accepted") {
          setAnnouncement("The interview changed on the server. Your unsent answer is still here.");
        } else if (refreshed.kind === "failed") {
          setAnnouncement("The interview changed, but we could not refresh it. Your unsent answer is still here.");
        }
        return { post: { kind: "rejected" }, refresh: refreshed };
      } else {
        setAnnouncement("That action could not be completed. Your unsent answer is still here.");
        return { post: { kind: "rejected" }, refresh: null };
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

  const beginAudio = useCallback(async (): Promise<{ attemptId: string; stateVersion: number } | null> => {
    const envelope = newEnvelope();
    if (envelope === null) return null;
    const result = await execute({
      ...envelope,
      command_type: "begin_answer",
      payload: { recording_type: "audio", client_attempt_id: crypto.randomUUID() },
    });
    if (
      result.post.kind !== "accepted"
    ) return null;
    if (result.refresh?.kind === "accepted") {
      if (
        result.refresh.live.conversation_state !== "listening"
        || result.refresh.live.active_attempt?.recording_type !== "audio"
      ) return null;
      return {
        attemptId: result.refresh.live.active_attempt.id,
        stateVersion: result.refresh.live.state_version,
      };
    }
    return result.post.result.state === "listening" && result.post.result.active_attempt_id !== null
      ? { attemptId: result.post.result.active_attempt_id, stateVersion: result.post.result.state_version }
      : null;
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

  const executeRecorderRequest = useCallback(async (
    authority: { state_version: number },
    commandType: "pause" | "resume" | "keep_speaking" | "cancel_attempt" | "finish_answer",
    payload: Record<string, string>,
  ): Promise<CommandExecutionResult> => execute({
    command_id: crypto.randomUUID(),
    command_type: commandType,
    expected_state_version: authority.state_version,
    payload,
    contract_version: "coach_conversation_command_v1",
  } as ConversationCommandRequest), [execute]);

  const pauseAudio = useCallback(async () => {
    if (live === null) return "rejected" as RecorderTransitionOutcome;
    const result = await executeRecorderRequest(live, "pause", {});
    if (result.post.kind !== "accepted") return "rejected";
    if (result.refresh?.kind === "accepted") {
      return result.refresh.live.conversation_state === "paused" ? "accepted" : "rejected";
    }
    return result.post.result.state === "paused" ? "accepted_refresh_unavailable" : "rejected";
  }, [executeRecorderRequest, live]);

  const resumeAudio = useCallback(async () => {
    if (live === null) return "rejected" as RecorderTransitionOutcome;
    const result = await executeRecorderRequest(live, "resume", {});
    if (result.post.kind !== "accepted") return "rejected";
    if (result.refresh?.kind === "accepted") {
      return result.refresh.live.conversation_state !== "paused" ? "accepted" : "rejected";
    }
    return result.post.result.state !== "paused" ? "accepted_refresh_unavailable" : "rejected";
  }, [executeRecorderRequest, live]);

  const keepSpeakingAudio = useCallback(async (attemptId: string) => {
    if (live === null) return false;
    const result = await executeRecorderRequest(live, "keep_speaking", { attempt_id: attemptId });
    if (result.post.kind !== "accepted") return false;
    if (result.refresh?.kind === "accepted") {
      return result.refresh.live.conversation_state === "listening"
        && result.refresh.live.active_attempt?.id === attemptId;
    }
    return result.post.result.state === "listening" && result.post.result.active_attempt_id === attemptId;
  }, [executeRecorderRequest, live]);

  const resumePausedAuthority = useCallback(async (authority: ConversationLiveView) => {
    if (authority.conversation_state !== "paused") {
      return {
        kind: "accepted",
        authority: {
          state: authority.conversation_state,
          stateVersion: authority.state_version,
          attemptId: authority.active_attempt?.id ?? null,
          resumed: false,
        },
      } as RecorderAuthorityResult;
    }
    const result = await executeRecorderRequest(authority, "resume", {});
    if (result.refresh?.kind === "accepted") {
      return {
        kind: "accepted",
        authority: {
          state: result.refresh.live.conversation_state,
          stateVersion: result.refresh.live.state_version,
          attemptId: result.refresh.live.active_attempt?.id ?? null,
          resumed: result.refresh.live.conversation_state === "listening",
        },
      } as RecorderAuthorityResult;
    }
    if (result.post.kind !== "accepted") return { kind: "rejected" } as RecorderAuthorityResult;
    return {
      kind: "accepted",
      authority: {
        state: result.post.result.state,
        stateVersion: result.post.result.state_version,
        attemptId: result.post.result.active_attempt_id,
        resumed: result.post.result.state === "listening",
      },
    } as RecorderAuthorityResult;
  }, [executeRecorderRequest]);

  const cancelAudio = useCallback(async (attemptId: string): Promise<RecorderCancelOutcome> => {
    if (live === null) return "rejected";
    const resumed = await resumePausedAuthority(live);
    if (
      resumed.kind !== "accepted"
      || resumed.authority.state !== "listening"
      || resumed.authority.attemptId !== attemptId
    ) return "rejected";
    const result = await executeRecorderRequest(
      { state_version: resumed.authority.stateVersion },
      "cancel_attempt",
      { attempt_id: attemptId },
    );
    const cancelled = result.post.kind === "accepted" && (
      result.refresh?.kind === "accepted"
        ? result.refresh.live.conversation_state === "asking"
        : result.post.result.state === "asking"
    );
    if (cancelled) return "cancelled";
    const freshestCancelAuthority = result.refresh?.kind === "accepted"
      ? await waitForLatestAuthority(result.refresh.readSequence)
      : result.refresh?.kind === "stale"
        ? await waitForLatestAuthority(result.refresh.readSequence)
        : null;
    if (freshestCancelAuthority !== null) {
      const freshAttemptId = freshestCancelAuthority.active_attempt?.id ?? null;
      if (freshAttemptId !== attemptId) return "authority_mismatch";
      if (freshestCancelAuthority.conversation_state === "paused") return "remain_paused";
      if (freshestCancelAuthority.conversation_state === "listening") return "resumed_pending";
      return "authority_mismatch";
    }
    return resumed.authority.resumed ? "resumed_pending" : "rejected";
  }, [executeRecorderRequest, live, resumePausedAuthority, waitForLatestAuthority]);

  const discardAudioRecovery = useCallback(async (attemptId: string) => {
    if (live === null) return false;
    const resumed = await resumePausedAuthority(live);
    if (resumed.kind !== "accepted" || resumed.authority.state !== "listening") return false;
    const cancelled = await executeRecorderRequest(
      { state_version: resumed.authority.stateVersion },
      "cancel_attempt",
      { attempt_id: attemptId },
    );
    return cancelled.post.kind === "accepted" && (
      cancelled.refresh?.kind === "accepted"
        ? cancelled.refresh.live.conversation_state === "asking"
        : cancelled.post.result.state === "asking"
    );
  }, [executeRecorderRequest, live, resumePausedAuthority]);

  const finishAudio = useCallback(async (attemptId: string, uploadId: string) => {
    if (live === null) return false;
    const resumed = await resumePausedAuthority(live);
    if (resumed.kind !== "accepted" || resumed.authority.state !== "listening") return false;
    const finished = await executeRecorderRequest({ state_version: resumed.authority.stateVersion }, "finish_answer", {
      attempt_id: attemptId,
      upload_id: uploadId,
    });
    return finished.post.kind === "accepted" && (
      finished.refresh?.kind === "accepted"
        ? finished.refresh.live.conversation_state === "processing_answer"
        : finished.post.result.state === "processing_answer"
    );
  }, [executeRecorderRequest, live, resumePausedAuthority]);

  const recorderAuthority = live ?? lastRecorderAuthority.current;

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <p aria-live="polite" className="mb-4 text-sm text-[var(--text-muted)]" role="status">
        {announcement}
      </p>

      <ConversationRecorder
        sessionId={sessionId}
        attemptId={recorderAuthority?.active_attempt?.recording_type === "audio"
          ? recorderAuthority.active_attempt.id
          : null}
        serverState={recorderAuthority?.conversation_state ?? "asking"}
        authorityAvailable={live !== null}
        authorityVersion={recorderAuthority?.state_version ?? -1}
        allowedCommands={live?.allowed_commands ?? []}
        silencePolicy={recorderAuthority?.silence_policy ?? { warning_ms: 4000, finish_prompt_ms: 9000 }}
        pending={pending || live === null}
        onBeginAudio={beginAudio}
        onPause={pauseAudio}
        onResume={resumeAudio}
        onKeepSpeaking={keepSpeakingAudio}
        onCancel={cancelAudio}
        onDiscardAndRetry={discardAudioRecovery}
        onFinishCommand={finishAudio}
        onAnnouncement={setAnnouncement}
      />

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
