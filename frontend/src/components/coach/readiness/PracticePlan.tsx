"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { getUpcomingInterviews, type InterviewRound } from "@/lib/api";
import {
  createPlan,
  fetchPlans,
  patchPlanItem,
  startPlan,
  type PracticePlan,
} from "@/lib/coachReadinessApi";

function roundLabel(round: InterviewRound): string {
  const date = round.scheduled_at
    ? new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(
        new Date(round.scheduled_at.endsWith("Z") ? round.scheduled_at : `${round.scheduled_at}Z`),
      )
    : "No date";
  return `${round.type.replaceAll("_", " ")} · ${round.interviewer_name ?? "Interview"} · ${date}`;
}

export function PracticePlan() {
  const [plan, setPlan] = useState<PracticePlan | null>(null);
  const [rounds, setRounds] = useState<InterviewRound[]>([]);
  const [loading, setLoading] = useState(true);
  const [drafting, setDrafting] = useState(false);
  const [minutes, setMinutes] = useState(30);
  const [roundId, setRoundId] = useState("");
  const [tooClose, setTooClose] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([fetchPlans(), getUpcomingInterviews(30).catch(() => [])])
      .then(([plans, upcoming]) => {
        setPlan(plans.active ?? plans.draft);
        setRounds(upcoming);
      })
      .catch(() => setError("This week's plan is unavailable."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const draft = async () => {
    setDrafting(true);
    setError(null);
    setTooClose(false);
    try {
      const created = await createPlan({
        minutes,
        target_round_id: roundId || null,
      });
      setPlan(created);
    } catch (caught) {
      if (caught instanceof Error && caught.message === "invalid_input") {
        setTooClose(true);
      } else {
        setError("Could not build a plan. Try again.");
      }
    } finally {
      setDrafting(false);
    }
  };

  const start = async () => {
    if (!plan) return;
    try {
      setPlan(await startPlan(plan.id));
    } catch {
      setError("Could not start the plan.");
    }
  };

  const setItem = async (itemId: string, action: "done" | "skipped" | "todo") => {
    if (!plan) return;
    try {
      setPlan(await patchPlanItem(plan.id, itemId, action));
    } catch {
      setError("Could not update that item.");
    }
  };

  return (
    <SectionCard
      title="This week's plan"
      description="A short, ordered plan built from your focus areas."
      actions={
        plan ? (
          <StatusBadge tone="info">
            {plan.done_count} of {plan.total_count} done
          </StatusBadge>
        ) : undefined
      }
    >
      {loading ? (
        <div className="h-20 animate-pulse rounded-[var(--radius-card)] bg-[var(--surface-3)]" />
      ) : plan ? (
        <div className="space-y-3">
          {plan.items.map((item) => (
            <div key={item.id} className="rounded-[var(--radius-card)] bg-[var(--surface-2)] p-3">
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="checkbox"
                  aria-label={`Mark ${item.title} done`}
                  checked={item.status === "done"}
                  disabled={item.auto}
                  onChange={(event) =>
                    void setItem(item.id, event.target.checked ? "done" : "todo")
                  }
                />
                <span
                  className={`min-w-0 flex-1 text-sm ${
                    item.status === "done"
                      ? "text-[var(--text-dim)] line-through"
                      : "text-[var(--text)]"
                  }`}
                >
                  {item.title}
                </span>
                <span className="font-mono text-xs text-[var(--text-dim)]">{item.minutes} min</span>
                {item.status !== "done" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => void setItem(item.id, "skipped")}
                  >
                    Skip
                  </Button>
                ) : null}
              </div>
              {item.auto && item.completed_at ? (
                <p className="mt-2 text-xs text-[var(--text-dim)]">
                  Ticked automatically when you finished a session on{" "}
                  {new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(
                    new Date(item.completed_at),
                  )}
                </p>
              ) : null}
            </div>
          ))}
          {plan.status === "draft" ? (
            <Button type="button" onClick={() => void start()}>
              Start plan
            </Button>
          ) : null}
          {plan.unallocated_minutes > 0 ? (
            <p className="text-xs text-[var(--text-dim)]">
              {plan.unallocated_minutes} minutes unallocated.
            </p>
          ) : null}
        </div>
      ) : (
        <div className="grid gap-3">
          <div className="grid gap-2 sm:grid-cols-[7rem_1fr]">
            <label className="grid gap-1 text-sm text-[var(--text)]">
              Minutes
              <input
                type="number"
                min={10}
                max={120}
                className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-sm text-[var(--text)]"
                value={minutes}
                onChange={(event) => setMinutes(Number(event.target.value))}
              />
            </label>
            <label className="grid gap-1 text-sm text-[var(--text)]">
              Upcoming round (optional)
              <select
                className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-sm text-[var(--text)]"
                value={roundId}
                onChange={(event) => setRoundId(event.target.value)}
              >
                <option value="">No round</option>
                {rounds.map((round) => (
                  <option key={round.id} value={round.id}>
                    {roundLabel(round)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div>
            <Button type="button" loading={drafting} onClick={() => void draft()}>
              Plan my week
            </Button>
          </div>
          {tooClose ? (
            <p className="text-sm text-[var(--danger)]" role="alert">
              Too close to the interview for a plan. Open the brief instead.
            </p>
          ) : null}
        </div>
      )}
      {error ? (
        <p className="mt-3 text-sm text-[var(--danger)]" role="alert">{error}</p>
      ) : null}
    </SectionCard>
  );
}
