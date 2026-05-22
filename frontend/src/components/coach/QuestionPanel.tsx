"use client";

import { QuestionPresentation } from "@/lib/api";
import { Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const CATEGORY_COLORS: Record<string, string> = {
  Technical: "bg-blue-900/40 text-blue-300",
  Behavioural: "bg-purple-900/40 text-purple-300",
  Situational: "bg-amber-900/40 text-amber-300",
  Domain: "bg-emerald-900/40 text-emerald-300",
  Culture: "bg-rose-900/40 text-rose-300",
  Commercial: "bg-cyan-900/40 text-cyan-300",
};

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: "text-emerald-400",
  medium: "text-amber-400",
  hard: "text-red-400",
};

interface QuestionPanelProps {
  question: QuestionPresentation;
}

function speakQuestion(text: string) {
  if ("speechSynthesis" in window) {
    const utt = new SpeechSynthesisUtterance(text);
    utt.lang = "en-GB";
    utt.rate = 0.9;
    window.speechSynthesis.speak(utt);
  }
}

export function QuestionPanel({ question }: QuestionPanelProps) {
  const catColor = CATEGORY_COLORS[question.category] ?? "bg-slate-700 text-slate-300";
  const diffColor = DIFFICULTY_COLORS[question.difficulty] ?? "text-slate-400";

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800 p-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${catColor}`}>
            {question.category}
          </span>
          <span className={`text-xs font-semibold capitalize ${diffColor}`}>
            {question.difficulty}
          </span>
        </div>
        <span className="text-xs text-slate-500">
          Q{question.num} / {question.total}
        </span>
      </div>

      <div className="mb-4 flex items-start justify-between gap-4">
        <p className="text-lg font-medium leading-relaxed text-slate-100">{question.text}</p>
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0 p-1.5 text-slate-500 hover:text-slate-200"
          onClick={() => speakQuestion(question.text)}
          title="Read question aloud"
        >
          <Volume2 className="h-4 w-4" />
        </Button>
      </div>

      {question.context && (
        <div className="rounded-lg border border-slate-600 bg-slate-700/40 p-3">
          <p className="text-xs text-slate-400">{question.context}</p>
        </div>
      )}
    </div>
  );
}
