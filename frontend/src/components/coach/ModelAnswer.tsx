"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Lightbulb } from "lucide-react";

interface ModelAnswerProps {
  modelAnswer: string | null;
}

export function ModelAnswer({ modelAnswer }: ModelAnswerProps) {
  const [expanded, setExpanded] = useState(false);

  if (!modelAnswer) return null;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm text-slate-400 hover:text-slate-200"
      >
        <span className="flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-amber-400" />
          Model Answer (STAR structure)
        </span>
        {expanded ? (
          <ChevronUp className="h-4 w-4" />
        ) : (
          <ChevronDown className="h-4 w-4" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-slate-700 px-4 py-3">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
            {modelAnswer}
          </p>
        </div>
      )}
    </div>
  );
}
