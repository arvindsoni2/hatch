"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";

interface ScoreRationaleProps {
  reasoning: string | null;
  keywordMatches: string[];
  keywordMisses: string[];
}

export function ScoreRationale({
  reasoning,
  keywordMatches,
  keywordMisses,
}: ScoreRationaleProps) {
  const showReasoning = reasoning && reasoning !== "local-keyword";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} />
        <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          Why Hatch surfaced this
        </h3>
      </div>

      {showReasoning && (
        <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>
          {reasoning}
        </p>
      )}

      {keywordMatches.length > 0 && (
        <div>
          <p className="text-xs font-medium mb-1.5" style={{ color: "var(--text-muted)" }}>
            Skills you have
          </p>
          <div className="flex flex-wrap gap-1.5">
            {keywordMatches.map((skill) => (
              <span
                key={skill}
                className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
                style={{ background: "var(--success-soft)", color: "var(--success)" }}
              >
                ✓ {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {keywordMisses.length > 0 && (
        <div>
          <p className="text-xs font-medium mb-1.5" style={{ color: "var(--text-muted)" }}>
            Skills they want that you&apos;re missing
          </p>
          <div className="flex flex-wrap gap-1.5">
            {keywordMisses.map((skill) => (
              <span
                key={skill}
                className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs"
                style={{
                  background: "var(--surface-2)",
                  color: "var(--text-dim)",
                  border: "1px solid var(--border)",
                }}
              >
                {skill}
              </span>
            ))}
          </div>
          <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
            Consider adding these to your profile if you have them.{" "}
            <Link href="/settings" className="underline" style={{ color: "var(--accent)" }}>
              Update profile
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}
