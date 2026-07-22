"use client";

import { SessionFeedbackReport } from "@/lib/api";
import { ScoreRadar } from "./ScoreRadar";
import { CheckCircle2, AlertCircle, BookOpen, CalendarDays, Trophy } from "lucide-react";

interface FeedbackReportProps {
  report: SessionFeedbackReport;
}

const SCORE_COLOR = (s: number) =>
  s >= 8 ? "text-emerald-400" : s >= 6 ? "text-amber-400" : "text-red-400";

export function FeedbackReport({ report }: FeedbackReportProps) {
  return (
    <div className="space-y-6">
      {report.report_state === "fallback" ? (
        <div className="rounded-lg border border-amber-800 bg-amber-950/20 px-4 py-3 text-sm text-amber-200">
          This report uses deterministic fallback feedback because the coaching narrative was unavailable.
        </div>
      ) : null}

      {/* Header */}
      <div className="flex flex-col items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 p-6 text-center">
        <Trophy className="h-8 w-8 text-amber-400" />
        {report.overall_score === null ? (
          <span className="text-xl font-semibold text-slate-300">No score available</span>
        ) : (
          <span className={`text-5xl font-bold tabular-nums ${SCORE_COLOR(report.overall_score)}`}>
            {report.overall_score.toFixed(1)}
            <span className="text-xl text-slate-500">/10</span>
          </span>
        )}
        <p className="text-sm text-slate-400">Overall Score</p>
      </div>

      {/* Radar + category scores */}
      <div className="flex flex-col gap-4 rounded-xl border border-slate-700 bg-slate-800 p-5 sm:flex-row sm:items-center">
        <div className="flex justify-center sm:flex-1">
          <ScoreRadar scores={report.category_scores} size={200} />
        </div>
        <div className="flex-1 space-y-2">
          {Object.entries(report.category_scores).map(([cat, score]) => (
            <div key={cat} className="flex items-center justify-between text-sm">
              <span className="text-slate-400">{cat}</span>
              <span className={`font-semibold ${SCORE_COLOR(score)}`}>{score.toFixed(1)}/10</span>
            </div>
          ))}
        </div>
      </div>

      {/* Executive summary */}
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
        <h3 className="mb-2 text-sm font-semibold text-slate-300">Executive Summary</h3>
        <p className="text-sm leading-relaxed text-slate-400">{report.executive_summary}</p>
      </div>

      {/* Strengths + improvements */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-emerald-400">
            <CheckCircle2 className="h-4 w-4" /> Strengths
          </h3>
          <ul className="space-y-2">
            {report.strengths.map((s, i) => (
              <li key={i} className="text-sm text-slate-300 before:mr-2 before:content-['·']">{s}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-400">
            <AlertCircle className="h-4 w-4" /> Areas to Improve
          </h3>
          <ul className="space-y-2">
            {report.improvement_areas.map((s, i) => (
              <li key={i} className="text-sm text-slate-300 before:mr-2 before:content-['·']">{s}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Coaching points */}
      {report.coaching_points.length > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-indigo-400">
            <BookOpen className="h-4 w-4" /> Coaching Points
          </h3>
          <ol className="space-y-2">
            {report.coaching_points.map((cp, i) => (
              <li key={i} className="flex gap-3 text-sm text-slate-300">
                <span className="shrink-0 font-mono text-indigo-500">{i + 1}.</span>
                {cp}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* 7-day practice plan */}
      {report.practice_plan.length > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-300">
            <CalendarDays className="h-4 w-4 text-indigo-400" /> 7-Day Practice Plan
          </h3>
          <div className="space-y-3">
            {report.practice_plan.map((day) => (
              <div key={day.day} className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-900/50 text-xs font-bold text-indigo-400">
                  {day.day}
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-slate-200">{day.focus}</p>
                  <p className="text-xs text-slate-400">{day.activity}</p>
                  {day.resource && (
                    <p className="text-xs text-indigo-400">{day.resource}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Readiness assessment */}
      <div className="rounded-xl border border-indigo-800 bg-indigo-900/20 p-4 text-center">
        <p className="text-sm font-medium text-indigo-300">
          {report.question_evaluations.length > 0
            ? "Keep practising — consistency is the key to interview success."
            : "Complete a full session to receive your readiness assessment."}
        </p>
      </div>
    </div>
  );
}
