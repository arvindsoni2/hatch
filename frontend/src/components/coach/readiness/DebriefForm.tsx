"use client";

import { useEffect, useState } from "react";
import {
  fetchDebrief,
  saveDebrief,
  skipDebrief,
  type DebriefQuestion,
  type DebriefRead,
} from "@/lib/coachReadinessApi";
import { formatInterviewTime } from "@/lib/formatInterviewTime";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

const OVERALL_LABELS = ["Poor", "Weak", "Okay", "Good", "Great"];
const EXPECTATION_LABELS = [
  { value: "yes", label: "Yes" },
  { value: "unsure", label: "Unsure" },
  { value: "no", label: "No" },
] as const;

export interface DebriefFormProps {
  roundId: string;
}

function newQuestion(text: string): DebriefQuestion {
  return {
    id: `custom-${Date.now()}`,
    text,
    source_ref: null,
    asked: true,
    rating: null,
    story_id: null,
    note: null,
  };
}

export function DebriefForm({ roundId }: DebriefFormProps) {
  const [debrief, setDebrief] = useState<DebriefRead | null>(null);
  const [questions, setQuestions] = useState<DebriefQuestion[]>([]);
  const [overall, setOverall] = useState<number | null>(null);
  const [expectation, setExpectation] = useState<"yes" | "unsure" | "no" | null>(null);
  const [wentWell, setWentWell] = useState("");
  const [doDifferently, setDoDifferently] = useState("");
  const [quickAdd, setQuickAdd] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    fetchDebrief(roundId)
      .then((value) => {
        if (!active) return;
        setDebrief(value);
        setQuestions(value.questions);
        setOverall(value.overall);
        setExpectation(value.expectation);
        setWentWell(value.went_well ?? "");
        setDoDifferently(value.do_differently ?? "");
      })
      .catch(() => {
        if (active) setDebrief(null);
      });
    return () => {
      active = false;
    };
  }, [roundId]);

  if (!debrief) return null;

  const addQuestion = () => {
    const text = quickAdd.trim();
    if (!text) return;
    setQuestions((current) => [...current, newQuestion(text)]);
    setQuickAdd("");
  };

  const toggleAsked = (id: string) => {
    setQuestions((current) =>
      current.map((item) =>
        item.id === id ? { ...item, asked: !item.asked } : item,
      ),
    );
  };

  const handleSave = async () => {
    if (overall == null || saving) return;
    setSaving(true);
    setError("");
    try {
      const saved = await saveDebrief(roundId, {
        expected_version: debrief.version,
        overall,
        expectation,
        questions,
        went_well: wentWell || null,
        do_differently: doDifferently || null,
        notes_text: null,
      });
      setDebrief(saved);
      setQuestions(saved.questions);
    } catch (failure) {
      const status = (failure as { status?: number }).status;
      setError(
        status === 409
          ? "This debrief changed elsewhere. Your draft is kept."
          : "Could not save the debrief. Try again.",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async () => {
    setSaving(true);
    setError("");
    try {
      setDebrief(await skipDebrief(roundId, debrief.version));
    } catch {
      setError("Could not skip this debrief. Try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard
      title="How did it go?"
      description={
        debrief.scheduled_at
          ? `Round finished ${formatInterviewTime(debrief.scheduled_at)}`
          : "Only your overall rating is needed."
      }
      actions={<StatusBadge tone={debrief.status === "saved" ? "success" : "neutral"}>{debrief.status}</StatusBadge>}
    >
      <div className="space-y-5">
        <div>
          <h4 className="mb-2 text-sm font-semibold text-[var(--text)]">
            Questions you were asked
          </h4>
          {questions.length === 0 ? (
            <p className="text-sm text-[var(--text-dim)]">No likely questions available.</p>
          ) : (
            <ul className="space-y-2">
              {questions.map((question) => (
                <li key={question.id}>
                  <label className="flex min-h-11 items-start gap-2 text-sm text-[var(--text)]">
                    <input
                      type="checkbox"
                      checked={question.asked}
                      onChange={() => toggleAsked(question.id)}
                      className="mt-1 h-4 w-4"
                    />
                    <span>{question.text}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="min-w-0 flex-1 text-sm text-[var(--text)]">
              Quick-add question
              <input
                value={quickAdd}
                onChange={(event) => setQuickAdd(event.target.value)}
                className="mt-1 min-h-9 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-sm text-[var(--text)]"
              />
            </label>
            <Button type="button" variant="outline" size="sm" onClick={addQuestion}>
              Add
            </Button>
          </div>
        </div>

        <fieldset>
          <legend className="mb-2 text-sm font-semibold text-[var(--text)]">
            Overall feeling
          </legend>
          <div className="flex flex-wrap gap-2">
            {OVERALL_LABELS.map((label, index) => {
              const value = index + 1;
              return (
                <button
                  key={label}
                  type="button"
                  aria-pressed={overall === value}
                  aria-label={`${value} ${label}`}
                  onClick={() => setOverall(value)}
                  className={`h-11 min-w-11 rounded-[var(--radius-control)] border px-2 text-sm ${
                    overall === value
                      ? "bg-[var(--accent)] text-[var(--on-accent)]"
                      : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text)]"
                  }`}
                >
                  {value}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div>
          <h4 className="mb-2 text-sm font-semibold text-[var(--text)]">
            Do you expect to progress?
          </h4>
          <div className="flex flex-wrap gap-2">
            {EXPECTATION_LABELS.map((item) => (
              <button
                key={item.value}
                type="button"
                aria-pressed={expectation === item.value}
                onClick={() => setExpectation(item.value)}
                className={`min-h-9 rounded-[var(--radius-control)] border px-3 text-sm ${
                  expectation === item.value
                    ? "border-[var(--accent)] text-[var(--accent)]"
                    : "border-[var(--border)] text-[var(--text)]"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <label className="block text-sm text-[var(--text)]">
          Went well
          <textarea
            value={wentWell}
            onChange={(event) => setWentWell(event.target.value)}
            maxLength={1_000}
            className="mt-1 min-h-20 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)]"
          />
        </label>
        <label className="block text-sm text-[var(--text)]">
          Do differently
          <textarea
            value={doDifferently}
            onChange={(event) => setDoDifferently(event.target.value)}
            maxLength={1_000}
            className="mt-1 min-h-20 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)]"
          />
        </label>

        {error ? <p role="status" className="text-sm text-[var(--danger)]">{error}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => void handleSave()} disabled={overall == null || saving}>
            Save debrief
          </Button>
          <Button type="button" variant="ghost" onClick={() => void handleSkip()} disabled={saving}>
            Skip this one
          </Button>
        </div>
      </div>
    </SectionCard>
  );
}
