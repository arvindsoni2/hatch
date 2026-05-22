"use client";

import { SessionQuestion } from "@/lib/api";
import { CheckCircle2, Circle, SkipForward } from "lucide-react";

interface QuestionNavProps {
  questions: SessionQuestion[];
  answeredIds: Set<string>;
  currentId: string | null;
  onSelect: (question: SessionQuestion) => void;
}

const CATEGORY_DOT: Record<string, string> = {
  Technical: "bg-blue-500",
  Behavioural: "bg-purple-500",
  Situational: "bg-amber-500",
  Domain: "bg-emerald-500",
  Culture: "bg-rose-500",
  Commercial: "bg-cyan-500",
};

export function QuestionNav({ questions, answeredIds, currentId, onSelect }: QuestionNavProps) {
  return (
    <div className="space-y-1">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
        Questions ({answeredIds.size}/{questions.length})
      </p>
      {questions.map((q) => {
        const answered = answeredIds.has(q.id);
        const isCurrent = q.id === currentId;
        return (
          <button
            key={q.id}
            onClick={() => onSelect(q)}
            className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
              isCurrent
                ? "bg-indigo-900/40 text-indigo-300"
                : "text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
            }`}
          >
            {answered ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
            ) : (
              <Circle className="h-4 w-4 shrink-0 text-slate-600" />
            )}
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${CATEGORY_DOT[q.category] ?? "bg-slate-600"}`}
            />
            <span className="truncate">Q{q.order_in_session}. {q.text.slice(0, 50)}{q.text.length > 50 ? "…" : ""}</span>
          </button>
        );
      })}
    </div>
  );
}
