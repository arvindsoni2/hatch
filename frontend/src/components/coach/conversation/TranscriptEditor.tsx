"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { ConversationCommandType, ConversationTranscriptVersionRead } from "@/lib/api";
import type { ReviewCommandHandler } from "./AnswerReview";

interface TranscriptEditorProps {
  attempt: {
    id: string;
    attempt_number: number;
    transcript_version: ConversationTranscriptVersionRead | null;
  };
  allowedCommands: ReadonlyArray<ConversationCommandType>;
  pending: boolean;
  onCommand: ReviewCommandHandler;
}

export function TranscriptEditor({ attempt, allowedCommands, pending, onCommand }: TranscriptEditorProps) {
  const transcript = attempt.transcript_version;
  const [editedTranscript, setEditedTranscript] = useState(transcript?.transcript ?? "");
  const canEdit = transcript !== null && allowedCommands.includes("edit_transcript");
  const codePointCount = Array.from(editedTranscript.normalize("NFC").replace(/\r\n?/g, "\n")).length;
  const normalizedCorrection = editedTranscript.normalize("NFC").replace(/\r\n?/g, "\n").trim();

  if (transcript === null) return null;

  return (
    <section aria-label="Transcript" className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <h2 className="text-base font-semibold text-[var(--text)]">Transcript</h2>
      <p className="mt-2 text-xs text-[var(--text-muted)]">
        {transcript.source === "candidate_edit"
          ? `Candidate correction, version ${transcript.version_number}`
          : `Transcript version ${transcript.version_number}`}
      </p>
      {canEdit ? (
        <div className="mt-3 space-y-3">
          <p className="text-sm text-[var(--text-muted)]">
            Editing corrects transcription and re-runs answer and evidence review.
          </p>
          <p className="text-sm text-[var(--text-muted)]">
            Delivery observations remain based on the original audio.
          </p>
          <label className="block text-sm font-semibold text-[var(--text)]" htmlFor={`transcript-edit-${attempt.id}`}>
            Corrected transcript
          </label>
          <textarea
            id={`transcript-edit-${attempt.id}`}
            value={editedTranscript}
            rows={8}
            disabled={pending}
            onChange={(event) => setEditedTranscript(event.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          />
          <p className="text-xs text-[var(--text-muted)]">{codePointCount} of 30,000 characters</p>
          <Button
            type="button"
            disabled={pending || normalizedCorrection.length < 1 || codePointCount > 30_000}
            onClick={() => onCommand("edit_transcript", {
              attempt_id: attempt.id,
              transcript: normalizedCorrection,
              edit_reason: "transcription_error",
            })}
          >
            Re-run review with corrected transcript
          </Button>
        </div>
      ) : (
        <p className="mt-3 whitespace-pre-wrap text-sm text-[var(--text-muted)]">{transcript.transcript}</p>
      )}
    </section>
  );
}
