"use client";

import { useEffect, useState } from "react";
import {
  fetchDebrief,
  saveDebrief,
  skipDebrief,
  type DebriefQuestion,
  type DebriefRead,
} from "@/lib/coachReadinessApi";
import { listStories, type StoryListItem } from "@/lib/api";
import { formatInterviewTime } from "@/lib/formatInterviewTime";
import { useDisplayTimeZone } from "@/lib/useDisplayTimeZone";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

const OVERALL_LABELS = ["Poor", "Weak", "Okay", "Good", "Great"];
const EXPECTATION_LABELS = [
  { value: "yes", label: "Yes" },
  { value: "unsure", label: "Not sure" },
  { value: "no", label: "No" },
] as const;
const STATUS_LABELS = {
  due: "Due",
  draft: "Draft",
  saved: "Saved",
  skipped: "Skipped",
} as const;

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
  const timeZone = useDisplayTimeZone();
  const [debrief, setDebrief] = useState<DebriefRead | null>(null);
  const [version, setVersion] = useState(0);
  const [questions, setQuestions] = useState<DebriefQuestion[]>([]);
  const [stories, setStories] = useState<StoryListItem[]>([]);
  const [overall, setOverall] = useState<number | null>(null);
  const [expectation, setExpectation] = useState<"yes" | "unsure" | "no" | null>(null);
  const [wentWell, setWentWell] = useState("");
  const [doDifferently, setDoDifferently] = useState("");
  const [quickAdd, setQuickAdd] = useState("");
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [savedAck, setSavedAck] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    fetchDebrief(roundId)
      .then((value) => {
        if (!active) return;
        setDebrief(value);
        setVersion(value.version);
        setQuestions(value.questions);
        setOverall(value.overall);
        setExpectation(value.expectation);
        setWentWell(value.went_well ?? "");
        setDoDifferently(value.do_differently ?? "");
      })
      .catch(() => {
        if (active) setDebrief(null);
      });
    listStories({ limit: 100 })
      .then((result) => {
        if (active) setStories(result.items);
      })
      .catch(() => {
        if (active) setStories([]);
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

  const updateQuestion = (id: string, changes: Partial<DebriefQuestion>) => {
    setQuestions((current) =>
      current.map((item) => (item.id === id ? { ...item, ...changes } : item)),
    );
  };

  const handleSave = async () => {
    if (overall == null || saving) return;
    setSaving(true);
    setError("");
    setConflict(false);
    try {
      const saved = await saveDebrief(roundId, {
        expected_version: version,
        overall,
        expectation,
        questions,
        went_well: wentWell || null,
        do_differently: doDifferently || null,
        notes_text: null,
      });
      setDebrief(saved);
      setVersion(saved.version);
      setQuestions(saved.questions);
      setSavedAck(
        `Saved. ${questions.filter((item) => item.asked).length} questions added to this round.`,
      );
    } catch (failure) {
      const status = (failure as { status?: number }).status;
      if (status === 409) {
        setConflict(true);
        setError("Reload and re-apply");
      } else {
        setError("Could not save the debrief. Try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  const reloadAndReapply = async () => {
    try {
      const fresh = await fetchDebrief(roundId);
      setVersion(fresh.version);
      setDebrief((current) => (current ? { ...current, version: fresh.version } : current));
      setConflict(false);
      setError("Reloaded. Your draft is kept; save again to re-apply.");
    } catch {
      setError("Could not reload the debrief. Try again.");
    }
  };

  const handleSkip = async () => {
    setSaving(true);
    setError("");
    try {
      const skipped = await skipDebrief(roundId, version);
      setDebrief(skipped);
      setVersion(skipped.version);
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
          ? `Round finished ${formatInterviewTime(debrief.scheduled_at, timeZone)}`
          : "Only your overall rating is needed."
      }
      actions={
        <StatusBadge tone={debrief.status === "saved" ? "success" : "neutral"}>
          {STATUS_LABELS[debrief.status]}
        </StatusBadge>
      }
    >
      <div className="space-y-5">
        <div>
          <h4 className="mb-2 text-sm font-semibold text-[var(--text)]">
            Questions you were asked
          </h4>
          {questions.length === 0 ? (
            <p className="text-sm text-[var(--text-dim)]">No likely questions available.</p>
          ) : (
            <ul className="space-y-3">
              {questions.map((question) => (
                <li key={question.id}>
                  <label className="flex min-h-11 items-start gap-2 text-sm text-[var(--text)]">
                    <input
                      type="checkbox"
                      checked={question.asked}
                      onChange={() => updateQuestion(question.id, { asked: !question.asked })}
                      className="mt-1 h-4 w-4"
                    />
                    <span>
                      {question.text}
                      {question.id.startsWith("custom-") ? (
                        <span className="ml-2 text-xs text-[var(--text-dim)]">Added by you</span>
                      ) : null}
                    </span>
                  </label>
                  {question.asked ? (
                    <div className="ml-6 mt-2 space-y-2">
                      <div>
                        <span className="mr-2 text-xs text-[var(--text-dim)]">How did it go?</span>
                        {[1, 2, 3, 4, 5].map((value) => (
                          <button
                            key={value}
                            type="button"
                            aria-pressed={question.rating === value}
                            aria-label={`Question rating ${value} of 5`}
                            onClick={() => updateQuestion(question.id, { rating: value })}
                            className={`mr-1 h-9 min-w-9 rounded-[var(--radius-control)] border text-sm ${
                              question.rating === value
                                ? "bg-[var(--accent)] text-[var(--on-accent)]"
                                : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text)]"
                            }`}
                          >
                            {value}
                          </button>
                        ))}
                      </div>
                      <label className="block text-xs text-[var(--text-dim)]">
                        Story you used
                        <select
                          value={question.story_id ?? ""}
                          onChange={(event) =>
                            updateQuestion(question.id, {
                              story_id: event.target.value || null,
                            })
                          }
                          className="ml-2 min-h-9 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-2 text-sm text-[var(--text)]"
                        >
                          <option value="">None</option>
                          {stories.map((story) => (
                            <option key={story.id} value={story.id}>
                              {story.title}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="block text-xs text-[var(--text-dim)]">
                        Note
                        <input
                          value={question.note ?? ""}
                          onChange={(event) =>
                            updateQuestion(question.id, { note: event.target.value })
                          }
                          maxLength={200}
                          placeholder="One line, optional"
                          className="ml-2 min-h-9 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-2 text-sm text-[var(--text)]"
                        />
                      </label>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="min-w-0 flex-1 text-sm text-[var(--text)]">
              Another question
              <input
                value={quickAdd}
                onChange={(event) => setQuickAdd(event.target.value)}
                placeholder="Type a question you were asked"
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
            Overall, how did it go?
          </legend>
          <div className="flex flex-wrap items-center gap-2">
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
            <span className="text-sm text-[var(--text-dim)]">
              {overall ? OVERALL_LABELS[overall - 1] : ""}
            </span>
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-sm font-semibold text-[var(--text)]">
            Do you expect to move to the next round?
          </legend>
          <div className="flex flex-wrap gap-2">
            {EXPECTATION_LABELS.map((item) => (
              <button
                key={item.value}
                type="button"
                aria-pressed={expectation === item.value}
                onClick={() => setExpectation(item.value)}
                className={`min-h-11 rounded-[var(--radius-control)] border px-3 text-sm ${
                  expectation === item.value
                    ? "border-[var(--accent)] text-[var(--accent)]"
                    : "border-[var(--border)] text-[var(--text)]"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="block text-sm text-[var(--text)]">
          What went well
          <textarea
            value={wentWell}
            onChange={(event) => setWentWell(event.target.value)}
            maxLength={1_000}
            placeholder="Optional"
            className="mt-1 min-h-20 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)]"
          />
        </label>
        <label className="block text-sm text-[var(--text)]">
          What you would do differently
          <textarea
            value={doDifferently}
            onChange={(event) => setDoDifferently(event.target.value)}
            maxLength={1_000}
            placeholder="Optional"
            className="mt-1 min-h-20 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)]"
          />
        </label>

        {error ? (
          <div className="flex flex-wrap items-center gap-2">
            <p role="status" className="text-sm text-[var(--danger)]">{error}</p>
            {conflict ? (
              <Button type="button" variant="outline" size="sm" onClick={() => void reloadAndReapply()}>
                Reload and re-apply
              </Button>
            ) : null}
          </div>
        ) : null}
        {savedAck ? <p role="status" aria-live="polite" className="text-sm text-[var(--success)]">{savedAck}</p> : null}
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
