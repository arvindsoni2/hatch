"use client";

import { TailoredCV, JDAnalysisResult } from "@/lib/api";

interface CVPreviewProps {
  cv: TailoredCV;
  jdAnalysis?: JDAnalysisResult | null;
}

function SafeHighlight({ text, keywords }: { text: string; keywords: string[] }) {
  if (!keywords.length) return <>{text}</>;
  const escaped = keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, i) =>
        pattern.test(part) ? (
          <mark key={i} className="bg-blue-500/30 text-blue-200 rounded px-0.5">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

export function CVPreview({ cv, jdAnalysis }: CVPreviewProps) {
  const keywords = jdAnalysis
    ? [
        ...jdAnalysis.ats_keywords.technical,
        ...jdAnalysis.ats_keywords.methodologies,
        ...jdAnalysis.ats_keywords.domain,
      ]
    : [];

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800 p-6 font-mono text-sm">
      {/* Fabrication warnings */}
      {cv.fabrication_warnings.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-700 bg-amber-900/20 p-3">
          <p className="mb-1 text-xs font-semibold text-amber-400">
            ⚠ Fabrication Warnings ({cv.fabrication_warnings.length})
          </p>
          {cv.fabrication_warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-300">
              {w}
            </p>
          ))}
        </div>
      )}

      {/* Summary */}
      <section className="mb-5">
        <h3 className="mb-2 border-b border-slate-600 pb-1 text-xs font-bold uppercase tracking-widest text-indigo-400">
          Professional Summary
        </h3>
        <p className="text-slate-300 leading-relaxed">
          <SafeHighlight text={cv.summary} keywords={keywords} />
        </p>
      </section>

      {/* Skills */}
      {cv.skills.length > 0 && (
        <section className="mb-5">
          <h3 className="mb-2 border-b border-slate-600 pb-1 text-xs font-bold uppercase tracking-widest text-indigo-400">
            Core Skills
          </h3>
          {cv.skills.map((sg, i) => (
            <div key={i} className="mb-1 flex gap-2">
              {sg.display_name && (
                <span className="min-w-[140px] text-xs font-semibold text-slate-400">
                  {sg.display_name}:
                </span>
              )}
              <span className="text-slate-300 text-xs">
                <SafeHighlight text={(sg.items ?? []).join("  ·  ")} keywords={keywords} />
              </span>
            </div>
          ))}
        </section>
      )}

      {/* Experience */}
      {cv.experience.length > 0 && (
        <section className="mb-5">
          <h3 className="mb-3 border-b border-slate-600 pb-1 text-xs font-bold uppercase tracking-widest text-indigo-400">
            Professional Experience
          </h3>
          {cv.experience.map((exp, i) => (
            <div key={i} className="mb-4">
              <div className="flex items-baseline justify-between">
                <span className="font-bold text-slate-100">{exp.role}</span>
                <span className="text-xs text-slate-500">{exp.period}</span>
              </div>
              <p className="mb-2 italic text-slate-400">{exp.company}</p>
              <ul className="space-y-1 pl-3">
                {exp.achievements.map((ach, j) => (
                  <li key={j} className="text-slate-300 before:mr-2 before:content-['•']">
                    <SafeHighlight text={ach} keywords={keywords} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      {/* Certifications */}
      {cv.certifications.length > 0 && (
        <section>
          <h3 className="mb-2 border-b border-slate-600 pb-1 text-xs font-bold uppercase tracking-widest text-indigo-400">
            Certifications
          </h3>
          <ul className="space-y-0.5 pl-3">
            {cv.certifications.map((cert, i) => (
              <li key={i} className="text-slate-300 before:mr-2 before:content-['•']">
                {cert}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ATS Keywords embedded note */}
      {cv.ats_keywords_embedded.length > 0 && (
        <div className="mt-4 rounded-lg bg-slate-700/40 p-3">
          <p className="text-xs text-slate-500">
            ATS keywords embedded:{" "}
            <span className="text-blue-400">{cv.ats_keywords_embedded.join(", ")}</span>
          </p>
        </div>
      )}
    </div>
  );
}
