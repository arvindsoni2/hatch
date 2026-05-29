"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";
import type { Job } from "@/lib/api";

interface ScoreRationaleProps {
  job: Job;
}

export function ScoreRationale({ job }: ScoreRationaleProps) {
  const {
    match_score,
    scoring_method,
    fit_reasoning,
    score_strengths,
    score_gaps,
  } = job;

  const scorePct = match_score != null ? Math.round(match_score * 100) : null;

  // Score colour
  const scoreColor =
    scorePct == null
      ? "var(--text-muted)"
      : scorePct >= 80
      ? "var(--success)"
      : scorePct >= 60
      ? "var(--warning)"
      : "var(--danger)";

  const isAI = scoring_method === "llm" || scoring_method === "semantic";
  const methodLabel = isAI ? "AI assessment" : "Quick estimate";

  return (
    <div
      className="rounded-xl p-6 space-y-5"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      {/* Header: score + method badge */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} />
          <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
            Match assessment
          </h2>
        </div>
        <div className="flex items-center gap-3">
          {scorePct != null && (
            <span
              className="text-3xl font-bold tabular-nums leading-none"
              style={{ color: scoreColor }}
            >
              {scorePct}%
            </span>
          )}
          {scoring_method && (
            <span
              className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
              style={{
                background: isAI ? "var(--accent-soft)" : "var(--surface-2)",
                color: isAI ? "var(--accent)" : "var(--text-dim)",
                border: "1px solid var(--border)",
              }}
            >
              {methodLabel}
            </span>
          )}
        </div>
      </div>

      {/* Fit reasoning */}
      {fit_reasoning && (
        <div>
          <p
            className="text-xs font-semibold mb-1.5 uppercase tracking-wide"
            style={{ color: "var(--text-muted)" }}
          >
            Why this is a fit
          </p>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>
            {fit_reasoning}
          </p>
        </div>
      )}

      {/* Strengths */}
      {score_strengths && score_strengths.length > 0 && (
        <div>
          <p
            className="text-xs font-semibold mb-1.5 uppercase tracking-wide"
            style={{ color: "var(--text-muted)" }}
          >
            Your strengths
          </p>
          <div className="flex flex-wrap gap-1.5">
            {score_strengths.map((s) => (
              <span
                key={s}
                className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
                style={{ background: "var(--success-soft)", color: "var(--success)" }}
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Gaps */}
      {score_gaps && score_gaps.length > 0 && (
        <div>
          <p
            className="text-xs font-semibold mb-1.5 uppercase tracking-wide"
            style={{ color: "var(--text-muted)" }}
          >
            Possible gaps
          </p>
          <div className="flex flex-wrap gap-1.5">
            {score_gaps.map((g) => (
              <span
                key={g}
                className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs"
                style={{
                  background: "var(--surface-2)",
                  color: "var(--text-dim)",
                  border: "1px solid var(--border)",
                }}
              >
                {g}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Nudge: no fit_reasoning */}
      {!fit_reasoning && scoring_method === "local" && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Upload your CV for more accurate matching.{" "}
          <Link
            href="/settings/profile"
            className="underline"
            style={{ color: "var(--accent)" }}
          >
            Go to profile
          </Link>
        </p>
      )}

      {!fit_reasoning && scoring_method !== "local" && scoring_method != null && (
        <p className="text-xs italic" style={{ color: "var(--text-muted)" }}>
          Analysing fit…
        </p>
      )}
    </div>
  );
}
