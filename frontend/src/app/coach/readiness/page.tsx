"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { PatternGroup } from "@/components/coach/readiness/PatternGroup";
import { PageContainer, PageHeader } from "@/components/ui/page-layout";
import { SectionCard } from "@/components/ui/section-card";
import {
  dismissPattern,
  fetchPatterns,
  undoPatternDismissal,
  type PatternGroupSection,
} from "@/lib/coachReadinessApi";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/coach", label: "Sessions" },
  { href: "/coach/stories", label: "Stories" },
  { href: "/coach/readiness", label: "Readiness" },
];

export default function ReadinessPage() {
  const [groups, setGroups] = useState<PatternGroupSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [lastDismissed, setLastDismissed] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(false);
    fetchPatterns(true)
      .then((result) => setGroups(result.groups))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const removePattern = (fingerprint: string) => {
    setGroups((current) =>
      current.map((group) => ({
        ...group,
        patterns: group.patterns.filter((pattern) => pattern.fingerprint !== fingerprint),
      })),
    );
  };

  const dismiss = async (fingerprint: string) => {
    try {
      await dismissPattern(fingerprint);
      removePattern(fingerprint);
      setLastDismissed(fingerprint);
    } catch {
      setError(true);
    }
  };

  const undo = async (fingerprint: string) => {
    try {
      await undoPatternDismissal(fingerprint);
      setLastDismissed(null);
      load();
    } catch {
      setError(true);
    }
  };

  const visibleGroups = groups
    .map((group) => ({
      ...group,
      patterns: group.patterns.filter((pattern) => !pattern.dismissed),
    }))
    .filter((group) => group.patterns.length > 0 || group.session_count < 2);

  return (
    <PageContainer className="px-4 py-8">
      <PageHeader
        title="Interview readiness"
        description="Your next interview, what to work on, and this week's practice. Built from your own sessions and stories."
      />

      <nav aria-label="Interview Coach sections" className="mb-6 flex gap-1 border-b border-[var(--border)]">
        {TABS.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={tab.href === "/coach/readiness" ? "page" : undefined}
            className={cn(
              "px-3 py-2 text-sm font-medium",
              tab.href === "/coach/readiness"
                ? "border-b-2 border-[var(--accent)] text-[var(--text)]"
                : "text-[var(--text-dim)] hover:text-[var(--text)]",
            )}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      <SectionCard
        title="Patterns"
        description="From your practice in the last 90 days, grouped by role and interview type. Dismiss anything that looks wrong."
      >
        {loading ? (
          <div className="space-y-3" aria-busy="true">
            {[1, 2, 3].map((item) => (
              <div key={item} className="h-24 animate-pulse rounded-[var(--radius-card)] bg-[var(--surface-3)]" />
            ))}
          </div>
        ) : error ? (
          <p className="text-sm text-[var(--danger)]" role="alert">
            Patterns are unavailable. Try again later.
          </p>
        ) : visibleGroups.length === 0 ? (
          <div className="rounded-[var(--radius-card)] border border-dashed border-[var(--border)] px-4 py-10 text-center">
            <p className="font-semibold text-[var(--text)]">No patterns yet</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-[var(--text-dim)]">
              Finish two practice sessions in the same role and interview type and Hatch will show what recurs.
            </p>
            <Link href="/coach" className="mt-4 inline-block text-sm font-semibold text-[var(--accent)] underline-offset-4 hover:underline">
              Start a practice session
            </Link>
          </div>
        ) : (
          <>
            {lastDismissed ? (
              <div className="mb-4 flex items-center justify-between gap-3 rounded-[var(--radius-control)] bg-[var(--surface-2)] px-3 py-2" role="status">
                <span className="text-sm text-[var(--text-dim)]">Pattern dismissed.</span>
                <button
                  type="button"
                  className="text-sm font-semibold text-[var(--accent)] underline-offset-4 hover:underline"
                  onClick={() => void undo(lastDismissed)}
                >
                  Undo
                </button>
              </div>
            ) : null}
            <div className="space-y-6">
              {visibleGroups.map((group) => (
                <PatternGroup
                  key={`${group.role_family}|${group.interview_type}|${group.contract_version}`}
                  group={group}
                  onDismiss={(fingerprint) => void dismiss(fingerprint)}
                  onUndo={(fingerprint) => void undo(fingerprint)}
                />
              ))}
            </div>
          </>
        )}
      </SectionCard>
    </PageContainer>
  );
}
