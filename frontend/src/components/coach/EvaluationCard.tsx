"use client";

import { AnswerEvaluation } from "@/lib/api";
import { ScoreRadar } from "./ScoreRadar";
import { CheckCircle2, AlertCircle, MessageSquare } from "lucide-react";

interface EvaluationCardProps {
  evaluation: AnswerEvaluation;
}

const SCORE_COLOR = (s: number) =>
  s >= 8 ? "text-emerald-400" : s >= 6 ? "text-amber-400" : "text-red-400";

const BAR_COLOR = (s: number) =>
  s >= 8 ? "bg-emerald-500" : s >= 6 ? "bg-amber-500" : "bg-red-500";

const DIMENSION_LABELS: Record<string, string> = {
  relevance: "Relevance",
  star_structure: "STAR Structure",
  technical_depth: "Technical Depth",
  conciseness: "Conciseness",
  communication: "Communication",
  impact_metrics: "Impact & Metrics",
};

export function EvaluationCard({ evaluation }: EvaluationCardProps) {
  if (
    (evaluation.evaluation_state ?? "completed") !== "completed" ||
    evaluation.overall === null
  ) {
    return (
      <div className="rounded-xl border border-amber-800 bg-amber-950/20 p-5">
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          <div>
            <h3 className="font-semibold text-slate-200">Evaluation could not be completed</h3>
            <p className="mt-1 text-sm text-slate-400">
              {evaluation.feedback || "Your answer was kept, but no score is available."}
            </p>
            {evaluation.retryable ? (
              <p className="mt-2 text-sm text-amber-300">You can submit the answer again.</p>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  const overall = evaluation.overall;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 space-y-5">
      {/* Overall */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-200">Answer Evaluation</h3>
        <span className={`text-2xl font-bold tabular-nums ${SCORE_COLOR(overall)}`}>
          {overall.toFixed(1)}<span className="text-sm text-slate-500">/10</span>
        </span>
      </div>

      {/* Dimension bars + radar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <div className="flex-1 space-y-2">
          {Object.entries(evaluation.scores).map(([key, val]) => (
            <div key={key}>
              <div className="mb-0.5 flex justify-between text-xs text-slate-400">
                <span>{DIMENSION_LABELS[key] ?? key}</span>
                <span className={SCORE_COLOR(val)}>{val}/10</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-slate-700">
                <div
                  className={`h-1.5 rounded-full ${BAR_COLOR(val)}`}
                  style={{ width: `${val * 10}%` }}
                />
              </div>
            </div>
          ))}
        </div>
        <ScoreRadar scores={evaluation.scores} size={160} />
      </div>

      {/* Feedback */}
      <p className="text-sm leading-relaxed text-slate-300">{evaluation.feedback}</p>

      {/* Strengths */}
      {evaluation.strengths.length > 0 && (
        <div>
          <p className="mb-2 flex items-center gap-1 text-xs font-semibold text-emerald-400">
            <CheckCircle2 className="h-3 w-3" /> Strengths
          </p>
          <ul className="space-y-1">
            {evaluation.strengths.map((s, i) => (
              <li key={i} className="text-sm text-slate-300 before:mr-2 before:content-['·']">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Improvements */}
      {evaluation.improvements.length > 0 && (
        <div>
          <p className="mb-2 flex items-center gap-1 text-xs font-semibold text-amber-400">
            <AlertCircle className="h-3 w-3" /> Improvements
          </p>
          <ul className="space-y-1">
            {evaluation.improvements.map((s, i) => (
              <li key={i} className="text-sm text-slate-300 before:mr-2 before:content-['·']">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Follow-up question */}
      {evaluation.follow_up_question && (
        <div className="rounded-lg border border-indigo-800 bg-indigo-900/20 p-3">
          <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-indigo-400">
            <MessageSquare className="h-3 w-3" /> Follow-up Question
          </p>
          <p className="text-sm text-indigo-300">{evaluation.follow_up_question}</p>
        </div>
      )}
    </div>
  );
}
