"use client";

import { CoverLetter } from "@/lib/api";

interface CLPreviewProps {
  coverLetter: CoverLetter;
}

const WORD_MIN = 250;
const WORD_MAX = 350;

export function CLPreview({ coverLetter }: CLPreviewProps) {
  const { subject_line, greeting, body_paragraphs, sign_off, word_count, key_keywords_used } =
    coverLetter;

  const wordCountColor =
    word_count > WORD_MAX
      ? "text-red-400"
      : word_count < WORD_MIN
        ? "text-amber-400"
        : "text-emerald-400";

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800 p-6">
      {/* Header row */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Cover Letter Preview
        </h3>
        <span className={`rounded-full px-3 py-0.5 text-xs font-medium ${wordCountColor} bg-slate-700`}>
          {word_count} words
        </span>
      </div>

      <div className="space-y-3 text-sm text-slate-300 leading-relaxed">
        {/* Subject */}
        {subject_line && (
          <p className="font-semibold text-slate-100">Re: {subject_line}</p>
        )}

        {/* Greeting */}
        <p>{greeting}</p>

        {/* Body */}
        {body_paragraphs.map((para, i) => (
          <p key={i}>{para}</p>
        ))}

        {/* Sign off */}
        <p className="pt-2">{sign_off}</p>
      </div>

      {/* Keywords used */}
      {key_keywords_used.length > 0 && (
        <div className="mt-4 border-t border-slate-700 pt-3">
          <p className="mb-2 text-xs text-slate-500">Keywords included:</p>
          <div className="flex flex-wrap gap-1">
            {key_keywords_used.map((kw) => (
              <span
                key={kw}
                className="rounded-full bg-blue-900/40 px-2 py-0.5 text-xs text-blue-300"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
