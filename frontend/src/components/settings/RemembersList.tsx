"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { formatInterviewTime } from "@/lib/formatInterviewTime";
import { useDisplayTimeZone } from "@/lib/useDisplayTimeZone";
import {
  deleteAllReadinessData,
  deleteMemoryKind,
  fetchMemoryInventory,
  type MemoryInventory,
  type MemoryKind,
} from "@/lib/coachReadinessApi";

const KIND_COPY: Record<MemoryKind, { label: string; description: string; effect: string }> = {
  dismissed_patterns: {
    label: "Dismissed patterns",
    description: "Patterns you dismissed.",
    effect:
      "Clears the patterns you dismissed. One may reappear if the evidence still supports it.",
  },
  focus_areas_and_plans: {
    label: "Focus areas and plans",
    description: "Your focus areas and this week's practice plans.",
    effect: "Deletes your focus areas and practice plans.",
  },
  briefs: {
    label: "Briefs",
    description: "Cached enhancement text; the brief re-assembles from your data.",
    effect: "Deletes the cached brief enhancement text. The brief re-assembles from your data.",
  },
  debriefs: {
    label: "Debriefs",
    description: "Your saved debriefs, including rough notes.",
    effect:
      "Deletes the saved debriefs. Ticked, it also clears the whole question list on each round whose debrief is deleted. Rounds without a debrief keep their questions.",
  },
  explain_tips: {
    label: "Explain tips",
    description: "Cached tips from pattern explanations.",
    effect: "Deletes the cached tips from pattern explanations.",
  },
  competency_overrides: {
    label: "Competency overrides",
    description: "Your renames and hidden competencies.",
    effect: "Deletes your competency renames and hidden competencies.",
  },
  job_competencies: {
    label: "Job description competencies",
    description: "Cached competencies extracted from the job description.",
    effect:
      "Deletes the cached job-description competencies. Coverage uses the deterministic list until the next extraction.",
  },
};

const PAGE_ORDER: MemoryKind[] = [
  "dismissed_patterns",
  "focus_areas_and_plans",
  "briefs",
  "debriefs",
  "explain_tips",
  "competency_overrides",
  "job_competencies",
];

function rowCount(count: number): string {
  return `${count} ${count === 1 ? "row" : "rows"}`;
}

export function RemembersList() {
  const timeZone = useDisplayTimeZone();
  const [inventory, setInventory] = useState<MemoryInventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [status, setStatus] = useState("");
  const [pendingKind, setPendingKind] = useState<MemoryKind | null>(null);
  const [clearQuestions, setClearQuestions] = useState(false);
  const [dialogError, setDialogError] = useState("");
  const [allError, setAllError] = useState("");
  const [confirmAll, setConfirmAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const kindTrigger = useRef<HTMLButtonElement | null>(null);
  const allTrigger = useRef<HTMLButtonElement | null>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const focusHeading = useRef(false);

  const refresh = useCallback(async () => {
    setLoadError("");
    try {
      setInventory(await fetchMemoryInventory());
    } catch {
      setInventory(null);
      setLoadError("What Hatch remembers is unavailable. Try again later.");
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      setInventory(await fetchMemoryInventory());
    } catch {
      setLoadError("What Hatch remembers is unavailable. Try again later.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (focusHeading.current && inventory !== null) {
      focusHeading.current = false;
      headingRef.current?.focus();
    }
  }, [inventory]);

  const retry = () => {
    focusHeading.current = true;
    void load();
  };

  const counts = new Map((inventory?.kinds ?? []).map((item) => [item.kind, item]));

  const removeKind = async (kind: MemoryKind) => {
    setBusy(true);
    setDialogError("");
    try {
      const result = await deleteMemoryKind(kind, kind === "debriefs" && clearQuestions);
      setStatus(`${KIND_COPY[kind].label}: removed ${result.removed}.`);
      setPendingKind(null);
      setClearQuestions(false);
      await refresh();
    } catch {
      setDialogError("Could not delete that. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const removeAll = async () => {
    setBusy(true);
    setAllError("");
    try {
      const result = await deleteAllReadinessData();
      const removed = Object.values(result.removed).reduce((total, count) => total + count, 0);
      setStatus(`Removed ${removed} readiness items.`);
      setConfirmAll(false);
      await refresh();
    } catch {
      setAllError("Could not delete all readiness data. Try again.");
    } finally {
      setBusy(false);
    }
  };

  if (loadError && inventory === null) {
    return (
      <SectionCard>
        <h2 className="m-0 mb-4 text-base font-semibold text-[var(--text)]" tabIndex={-1} ref={headingRef}>
          What Hatch remembers
        </h2>
        <p className="m-0 text-sm text-[var(--danger)]" role="alert">
          {loadError}
        </p>
        <Button type="button" variant="outline" size="sm" className="mt-3" onClick={retry}>
          Try again
        </Button>
      </SectionCard>
    );
  }

  return (
    <div className="space-y-4">
      <SectionCard>
        <h2
          className="m-0 text-base font-semibold text-[var(--text)] focus:outline-none"
          tabIndex={-1}
          ref={headingRef}
        >
          What Hatch remembers
        </h2>
        <p className="mb-4 mt-1 text-sm text-[var(--text-dim)]">
          Every kind of Coach readiness data, with when it last changed.
        </p>
        {loading && inventory === null ? (
          <div className="space-y-2" aria-busy="true">
            {[1, 2, 3, 4].map((item) => (
              <div key={item} className="h-12 animate-pulse rounded-[var(--radius-control)] bg-[var(--surface-2)]" />
            ))}
          </div>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            <li className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <p className="m-0 text-sm font-semibold text-[var(--text)]">Patterns</p>
                <p className="m-0 text-xs text-[var(--text-dim)]">
                  Derived from your practice sessions. Nothing is stored, so there is nothing to delete here.
                </p>
              </div>
              <Link className="text-sm font-medium text-[var(--accent)] underline-offset-4 hover:underline" href="/coach">
                Delete practice sessions in Coach
              </Link>
            </li>
            {PAGE_ORDER.map((kind) => {
              const summary = counts.get(kind);
              return (
                <li key={kind} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <p className="m-0 text-sm font-semibold text-[var(--text)]">
                      {KIND_COPY[kind].label}
                    </p>
                    <p className="m-0 text-xs text-[var(--text-dim)]">
                      {KIND_COPY[kind].description} · {rowCount(summary?.count ?? 0)} ·{" "}
                      {summary?.last_updated
                        ? `Last updated ${formatInterviewTime(summary.last_updated, timeZone)}`
                        : "Never updated"}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    aria-label={`Delete ${KIND_COPY[kind].label}`}
                    onClick={(event) => {
                      kindTrigger.current = event.currentTarget;
                      setStatus("");
                      setDialogError("");
                      setPendingKind(kind);
                      setClearQuestions(false);
                    }}
                  >
                    Delete
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
        {status ? <p className="mb-0 mt-3 text-sm text-[var(--success)]" role="status" aria-live="polite">{status}</p> : null}
        {loadError ? <p className="mb-0 mt-3 text-sm text-[var(--danger)]" role="alert">{loadError}</p> : null}
      </SectionCard>

      <SectionCard
        title="Delete all Coach readiness data"
        description="Every stored readiness item goes. Practice sessions, rounds, stories and Question Bank entries stay."
      >
        <Button
          type="button"
          variant="destructive"
          onClick={(event) => {
            allTrigger.current = event.currentTarget;
            setStatus("");
            setAllError("");
            setConfirmAll(true);
          }}
        >
          Delete all Coach readiness data
        </Button>
      </SectionCard>

      <AlertDialog
        open={pendingKind !== null}
        onOpenChange={(open) => {
          if (!open && busy) return;
          if (!open) {
            setPendingKind(null);
            setClearQuestions(false);
            setDialogError("");
          }
        }}
      >
        <AlertDialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            kindTrigger.current?.focus();
          }}
        >
          <AlertDialogTitle>
            Delete {pendingKind ? KIND_COPY[pendingKind].label.toLowerCase() : "this data"}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            {pendingKind ? KIND_COPY[pendingKind].effect : "This removes the stored rows for this kind."}
          </AlertDialogDescription>
          {pendingKind === "debriefs" ? (
            <label className="mt-3 flex min-h-11 items-start gap-2 text-sm text-[var(--text)]">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4"
                checked={clearQuestions}
                onChange={(event) => setClearQuestions(event.target.checked)}
              />
              Also clear questions on the round
            </label>
          ) : null}
          {dialogError ? (
            <p className="mb-0 mt-3 text-sm text-[var(--danger)]" role="alert">{dialogError}</p>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(event) => {
                event.preventDefault();
                if (pendingKind) void removeKind(pendingKind);
              }}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={confirmAll}
        onOpenChange={(open) => {
          if (open) {
            setConfirmAll(true);
            return;
          }
          if (busy) return;
          setConfirmAll(false);
          setAllError("");
        }}
      >
        <AlertDialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            allTrigger.current?.focus();
          }}
        >
          <AlertDialogTitle>Delete all Coach readiness data?</AlertDialogTitle>
          <AlertDialogDescription>
            This deletes every stored readiness item: dismissals, focus areas,
            plans, briefs, debriefs, explain tips, competency overrides and job
            description competencies. Your practice sessions, interview rounds,
            stories and Question Bank entries are untouched.
          </AlertDialogDescription>
          {allError ? (
            <p className="mb-0 mt-3 text-sm text-[var(--danger)]" role="alert">{allError}</p>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(event) => {
                event.preventDefault();
                void removeAll();
              }}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
              Delete all Coach readiness data
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
