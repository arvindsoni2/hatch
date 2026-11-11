"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { FocusAreaEditor } from "@/components/coach/readiness/FocusAreaEditor";
import { FocusAreas } from "@/components/coach/readiness/FocusAreas";
import { PatternGroup } from "@/components/coach/readiness/PatternGroup";
import { PracticePlan } from "@/components/coach/readiness/PracticePlan";
import { PageContainer, PageHeader } from "@/components/ui/page-layout";
import { SectionCard } from "@/components/ui/section-card";
import {
  dismissPattern,
  fetchFocusAreas,
  fetchPatterns,
  patchFocusArea,
  undoPatternDismissal,
  type FocusArea,
  type FocusGroup,
  type Pattern,
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
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastDismissed, setLastDismissed] = useState<string | null>(null);
  const [focusAreas, setFocusAreas] = useState<FocusArea[]>([]);
  const [focusCount, setFocusCount] = useState(0);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorInitial, setEditorInitial] = useState<{
    title?: string;
    dimension?: string;
    group?: FocusGroup;
  }>();
  const [editingArea, setEditingArea] = useState<FocusArea | undefined>();

  const load = () => {
    setLoading(true);
    setError(false);
    fetchPatterns(true)
      .then((result) => setGroups(result.groups))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  const loadFocus = () => {
    fetchFocusAreas()
      .then((result) => {
        setFocusAreas(result.items);
        setFocusCount(result.active_count);
      })
      .catch(() => setFocusAreas([]));
  };

  useEffect(() => {
    load();
    loadFocus();
  }, []);

  const openEditor = (initial?: {
    title?: string;
    dimension?: string;
    group?: FocusGroup;
  }) => {
    setEditingArea(undefined);
    setEditorInitial(initial);
    setEditorOpen(true);
  };

  const editArea = (area: FocusArea) => {
    setEditingArea(area);
    setEditorInitial(undefined);
    setEditorOpen(true);
  };

  const changeFocusStatus = async (area: FocusArea, status: FocusArea["status"]) => {
    setActionError(null);
    try {
      await patchFocusArea(area.id, {
        expected_version: area.version,
        status,
      });
      loadFocus();
    } catch (caught) {
      if (caught instanceof Error && caught.message === "version_conflict") {
        setActionError("This focus area changed. Reload and re-apply.");
      } else {
        setActionError("Could not update this focus area.");
      }
    }
  };

  const markAchieved = async (area: FocusArea) => {
    try {
      await patchFocusArea(area.id, {
        expected_version: area.version,
        status: "achieved",
      });
      loadFocus();
    } catch {
      setActionError("Could not mark this focus area achieved.");
    }
  };

  const workOnPattern = (pattern: Pattern) => {
    openEditor({
      title: `Work on ${pattern.dimension.replaceAll("_", " ")}`,
      dimension: pattern.dimension,
      group: pattern.group,
    });
  };

  const removePattern = (fingerprint: string) => {
    setGroups((current) =>
      current.map((group) => ({
        ...group,
        patterns: group.patterns.filter((pattern) => pattern.fingerprint !== fingerprint),
      })),
    );
  };

  const dismiss = async (fingerprint: string) => {
    setActionError(null);
    try {
      await dismissPattern(fingerprint);
      removePattern(fingerprint);
      setLastDismissed(fingerprint);
    } catch {
      setActionError("Could not dismiss this pattern. It is still here; try again.");
    }
  };

  const undo = async (fingerprint: string) => {
    setActionError(null);
    try {
      await undoPatternDismissal(fingerprint);
      setLastDismissed(null);
      load();
    } catch {
      setActionError("Could not undo the dismissal. The pattern stays dismissed; try again.");
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

      <div className="mb-6">
        <FocusAreas
          areas={focusAreas.filter((area) => area.status !== "archived")}
          activeCount={focusCount}
          onAdd={() => openEditor()}
          onMarkAchieved={(area) => void markAchieved(area)}
          onStatusChange={(area, status) => void changeFocusStatus(area, status)}
          onEdit={editArea}
        />
      </div>

      <div className="mb-6">
        <PracticePlan />
      </div>

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
            {actionError ? (
              <p className="mb-4 text-sm text-[var(--danger)]" role="status">
                {actionError}
              </p>
            ) : null}
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
                  onWorkOnThis={workOnPattern}
                />
              ))}
            </div>
          </>
        )}
      </SectionCard>

      <FocusAreaEditor
        open={editorOpen}
        initial={editorInitial}
        area={editingArea}
        onClose={() => setEditorOpen(false)}
        onSaved={loadFocus}
      />
    </PageContainer>
  );
}
