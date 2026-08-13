"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type {
  ConversationCommandType,
  ConversationReviewLevel,
  ConversationReviewLiveView,
} from "@/lib/api";
import { CodePointExcerpt } from "./CodePointExcerpt";

export type ReviewCommandHandler = (
  command: ConversationCommandType,
  payload: Record<string, unknown>,
) => void;

const LEVEL_LABELS: Record<ConversationReviewLevel, string> = {
  needs_work: "Needs work",
  developing: "Developing",
  interview_ready: "Interview-ready",
  strong: "Strong",
  not_assessed: "Not assessed",
};

const EVIDENCE_STATUS_LABELS = {
  supported: "Supported",
  partially_supported: "Partially supported",
  not_found: "Not found in selected evidence",
  conflicting: "Conflicts with approved evidence",
} as const;

interface AnswerReviewProps {
  live: ConversationReviewLiveView;
  pending: boolean;
  onCommand: ReviewCommandHandler;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <h2 className="text-base font-semibold text-[var(--text)]">{title}</h2>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

export function AnswerReview({ live, pending, onCommand }: AnswerReviewProps) {
  const attempt = live.active_attempt;
  const review = live.answer_review;
  const assessment = attempt?.self_assessment;
  const [comfortLevel, setComfortLevel] = useState<"low" | "medium" | "high">(
    assessment?.comfort_level ?? "medium",
  );
  const [feltComplete, setFeltComplete] = useState(assessment?.felt_complete ?? false);
  const [note, setNote] = useState(assessment?.note ?? "");
  const allowed = new Set(live.allowed_commands);
  const transcript = attempt?.transcript_version?.transcript ?? "";

  if (attempt === null || review === null) return null;

  const submitReflection = () => {
    const normalizedNote = note.trim();
    onCommand("record_self_assessment", {
      attempt_id: attempt.id,
      comfort_level: comfortLevel,
      felt_complete: feltComplete,
      note: normalizedNote.length > 0 ? normalizedNote : null,
    });
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Answer quality">
        {review.evaluation_state === "completed" ? (
          <>
            <p className="text-sm font-semibold text-[var(--text)]">
              Overall: {LEVEL_LABELS[review.answer_level]}
            </p>
            {Object.entries(review.dimensions).map(([name, dimension]) => (
              <article key={name} className="space-y-2 rounded-lg bg-[var(--surface-2)] p-3">
                <h3 className="text-sm font-semibold text-[var(--text)]">
                  {name.replaceAll("_", " ")}: {LEVEL_LABELS[dimension.level]}
                </h3>
                {dimension.rationale === null ? null : (
                  <p className="text-sm text-[var(--text-muted)]">{dimension.rationale}</p>
                )}
                {dimension.improvement === null ? null : (
                  <p className="text-sm text-[var(--text-muted)]">{dimension.improvement}</p>
                )}
                {dimension.evidence.map((span) => (
                  <CodePointExcerpt
                    key={`${span.transcript_start}:${span.transcript_end}`}
                    transcript={transcript}
                    span={span}
                  />
                ))}
              </article>
            ))}
          </>
        ) : (
          <p className="text-sm text-[var(--text-muted)]">
            Answer quality was unavailable for technical reasons. No performance level was created.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {allowed.has("accept_attempt") ? (
            <Button
              type="button"
              disabled={pending}
              onClick={() => onCommand("accept_attempt", { attempt_id: attempt.id })}
            >
              Accept attempt {attempt.attempt_number}
            </Button>
          ) : null}
          {allowed.has("request_coaching") ? (
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={() => onCommand("request_coaching", { attempt_id: attempt.id })}
            >
              Get coaching for attempt {attempt.attempt_number}
            </Button>
          ) : null}
        </div>
      </Panel>

      <Panel title="Delivery observations">
        <p className="text-sm font-semibold text-[var(--text)]">
          {LEVEL_LABELS[review.delivery.level]}
        </p>
        {review.delivery.observations.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">No delivery observations were available.</p>
        ) : (
          <ul className="space-y-2">
            {review.delivery.observations.map((observation) => (
              <li key={`${observation.severity}:${observation.label}`} className="text-sm text-[var(--text-muted)]">
                {observation.label}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Evidence check">
        <p className="text-sm font-semibold text-[var(--text)]">
          {LEVEL_LABELS[review.evidence_consistency]}
        </p>
        {review.evidence_findings.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">No material claims required an evidence check.</p>
        ) : (
          <div className="space-y-3">
            {review.evidence_findings.map((finding) => (
              <article key={finding.claim_id} className="rounded-lg bg-[var(--surface-2)] p-3">
                <h3 className="text-sm font-semibold text-[var(--text)]">
                  {EVIDENCE_STATUS_LABELS[finding.status]}
                </h3>
                {finding.source_label === null ? null : (
                  <p className="mt-1 text-xs font-semibold text-[var(--text-muted)]">{finding.source_label}</p>
                )}
                <p className="mt-2 text-sm text-[var(--text-muted)]">{finding.explanation}</p>
                <p className="mt-2 text-sm text-[var(--text-muted)]">{finding.candidate_action}</p>
              </article>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Your reflection">
        {allowed.has("record_self_assessment") ? (
          <div className="space-y-3">
            <label className="block text-sm font-semibold text-[var(--text)]" htmlFor="review-comfort-level">
              Comfort level
            </label>
            <select
              id="review-comfort-level"
              value={comfortLevel}
              disabled={pending}
              onChange={(event) => setComfortLevel(event.target.value as typeof comfortLevel)}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-[var(--text)]">
              <input
                type="checkbox"
                checked={feltComplete}
                disabled={pending}
                onChange={(event) => setFeltComplete(event.target.checked)}
              />
              My answer felt complete
            </label>
            <label className="block text-sm font-semibold text-[var(--text)]" htmlFor="review-reflection-note">
              Reflection note
            </label>
            <textarea
              id="review-reflection-note"
              value={note}
              disabled={pending}
              maxLength={2_000}
              rows={4}
              onChange={(event) => setNote(event.target.value)}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            />
            <Button type="button" disabled={pending} onClick={submitReflection}>
              Save reflection
            </Button>
          </div>
        ) : assessment === null || assessment === undefined ? (
          <p className="text-sm text-[var(--text-muted)]">No reflection was saved for this attempt.</p>
        ) : (
          <div className="space-y-1 text-sm text-[var(--text-muted)]">
            <p>Comfort level: {assessment.comfort_level}</p>
            <p>{assessment.felt_complete ? "The answer felt complete." : "The answer did not feel complete."}</p>
            {assessment.note === null ? null : <p>{assessment.note}</p>}
          </div>
        )}
        {allowed.has("return_to_review") ? (
          <Button
            type="button"
            variant="outline"
            disabled={pending}
            onClick={() => onCommand("return_to_review", {})}
          >
            Return to review
          </Button>
        ) : null}
      </Panel>

      {live.conversation_state === "coaching" && review.coaching !== null ? (
        <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 md:col-span-2">
          <h2 className="text-base font-semibold text-[var(--text)]">Coaching</h2>
          <div className="mt-3 space-y-2 text-sm text-[var(--text-muted)]">
            <p>{review.coaching.positive_observation}</p>
            <p>{review.coaching.priority_improvement}</p>
            <p>{review.coaching.suggested_structure}</p>
            <p>{review.coaching.practice_instruction}</p>
            <p>{review.coaching.example_revision}</p>
          </div>
        </section>
      ) : null}
    </div>
  );
}
