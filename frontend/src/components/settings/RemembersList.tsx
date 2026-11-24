"use client";

import { useCallback, useEffect, useState } from "react";
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
import {
  deleteAllReadinessData,
  deleteMemoryKind,
  fetchMemoryInventory,
  type MemoryInventory,
  type MemoryKind,
} from "@/lib/coachReadinessApi";

const KIND_COPY: Record<MemoryKind, { label: string; description: string }> = {
  dismissed_patterns: {
    label: "Dismissed patterns",
    description: "Fingerprints only.",
  },
  focus_areas_and_plans: {
    label: "Focus areas and plans",
    description: "Your focus areas and this week's practice plans.",
  },
  briefs: {
    label: "Briefs",
    description: "Cached enhancement text; the brief re-assembles from your data.",
  },
  debriefs: {
    label: "Debriefs",
    description: "Your saved debriefs, including rough notes.",
  },
  explain_tips: {
    label: "Explain tips",
    description: "Cached tips from pattern explanations.",
  },
  competency_overrides: {
    label: "Competency overrides",
    description: "Your renames and hidden competencies.",
  },
  job_competencies: {
    label: "Job description competencies",
    description: "Cached competencies extracted from the job description.",
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

function lastUpdatedLabel(value: string | null): string {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Never";
  return `Last updated ${date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

export function RemembersList() {
  const [inventory, setInventory] = useState<MemoryInventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [pendingKind, setPendingKind] = useState<MemoryKind | null>(null);
  const [clearQuestions, setClearQuestions] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setInventory(await fetchMemoryInventory());
    } catch {
      setError("What Hatch remembers is unavailable. Try again later.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = new Map((inventory?.kinds ?? []).map((item) => [item.kind, item]));

  const removeKind = async (kind: MemoryKind) => {
    setBusy(true);
    setError("");
    try {
      const result = await deleteMemoryKind(kind, kind === "debriefs" && clearQuestions);
      setStatus(`${KIND_COPY[kind].label}: removed ${result.removed}.`);
      setPendingKind(null);
      setClearQuestions(false);
      await load();
    } catch {
      setError("Could not delete that. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const removeAll = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await deleteAllReadinessData();
      const removed = Object.values(result.removed).reduce((total, count) => total + count, 0);
      setStatus(`Removed ${removed} readiness rows. Phase 1 data is untouched.`);
      setConfirmAll(false);
      await load();
    } catch {
      setError("Could not delete all readiness data. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <SectionCard
        title="What Hatch remembers"
        description="Every kind of Coach readiness data, with when it last changed."
      >
        {loading ? (
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
                      {KIND_COPY[kind].description} · {summary?.count ?? 0} rows ·{" "}
                      {lastUpdatedLabel(summary?.last_updated ?? null)}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
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
        {error ? <p className="mb-0 mt-3 text-sm text-[var(--danger)]" role="alert">{error}</p> : null}
        {status ? <p className="mb-0 mt-3 text-sm text-[var(--success)]" role="status" aria-live="polite">{status}</p> : null}
      </SectionCard>

      <SectionCard
        title="Delete all Coach readiness data"
        description="Every row in the eight readiness tables goes. Practice sessions, rounds, stories and Question Bank entries stay."
      >
        <Button type="button" variant="destructive" onClick={() => setConfirmAll(true)}>
          Delete all Coach readiness data
        </Button>
      </SectionCard>

      <AlertDialog
        open={pendingKind !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPendingKind(null);
            setClearQuestions(false);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogTitle>
            Delete {pendingKind ? KIND_COPY[pendingKind].label.toLowerCase() : "this data"}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            {pendingKind === "debriefs"
              ? "Deletes the saved debriefs. Ticked, it also clears the whole question list on each round whose debrief is deleted. Rounds without a debrief keep their questions."
              : "This removes the stored rows for this kind. It cannot be undone."}
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

      <AlertDialog open={confirmAll} onOpenChange={setConfirmAll}>
        <AlertDialogContent>
          <AlertDialogTitle>Delete all Coach readiness data?</AlertDialogTitle>
          <AlertDialogDescription>
            This empties every readiness table: dismissals, focus areas, plans,
            briefs, debriefs, explain tips, competency overrides and job
            description competencies. Your practice sessions, interview rounds,
            stories and Question Bank entries are untouched.
          </AlertDialogDescription>
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
