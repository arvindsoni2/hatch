"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  CoachReadinessError,
  createFocusArea,
  patchFocusArea,
  type FocusArea,
  type FocusGroup,
} from "@/lib/coachReadinessApi";

const DIMENSIONS = [
  "relevance", "structure", "specificity", "impact", "role_depth", "clarity", "conciseness",
];

const INPUT =
  "min-h-11 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-sm text-[var(--text)]";

export function FocusAreaEditor({
  open,
  initial,
  area,
  onClose,
  onSaved,
}: {
  open: boolean;
  initial?: { title?: string; dimension?: string; group?: FocusGroup };
  area?: FocusArea;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? area?.title ?? "");
  const [dimension, setDimension] = useState(initial?.dimension ?? area?.dimension ?? "specificity");
  const [roleFamily, setRoleFamily] = useState(
    initial?.group?.role_family ?? area?.group?.role_family ?? "",
  );
  const [interviewType, setInterviewType] = useState(
    initial?.group?.interview_type ?? area?.group?.interview_type ?? "",
  );
  const [contractVersion, setContractVersion] = useState(
    initial?.group?.contract_version
      ?? area?.group?.contract_version
      ?? "coach_conversational_report_v1",
  );
  const [useLevel, setUseLevel] = useState(
    area?.criteria.some((item) => item.kind === "level") ?? Boolean(initial?.group),
  );
  const [usePractice, setUsePractice] = useState(
    area?.criteria.some((item) => item.kind === "practice") ?? true,
  );
  const [practiceCount, setPracticeCount] = useState(
    area?.criteria.find((item) => item.kind === "practice")?.target ?? 3,
  );
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle(initial?.title ?? area?.title ?? "");
    setDimension(initial?.dimension ?? area?.dimension ?? "specificity");
    setRoleFamily(initial?.group?.role_family ?? area?.group?.role_family ?? "");
    setInterviewType(initial?.group?.interview_type ?? area?.group?.interview_type ?? "");
    setContractVersion(
      initial?.group?.contract_version
        ?? area?.group?.contract_version
        ?? "coach_conversational_report_v1",
    );
    setUseLevel(area?.criteria.some((item) => item.kind === "level") ?? Boolean(initial?.group));
    setUsePractice(area?.criteria.some((item) => item.kind === "practice") ?? true);
    setPracticeCount(area?.criteria.find((item) => item.kind === "practice")?.target ?? 3);
    setConflict(false);
    setError(null);
  }, [open, initial, area]);

  const group = roleFamily && interviewType
    ? {
        role_family: roleFamily,
        interview_type: interviewType,
        contract_version: contractVersion,
      }
    : null;

  const save = async () => {
    if (!title.trim()) return;
    if (!area && !useLevel && !usePractice) {
      setError("Choose at least one criterion.");
      return;
    }
    if (!area && useLevel && !group) {
      setError("A level criterion needs a role family and interview type.");
      return;
    }
    setSaving(true);
    setError(null);
    setConflict(false);
    try {
      if (area) {
        await patchFocusArea(area.id, {
          expected_version: area.version,
          title: title.trim(),
        });
      } else {
        await createFocusArea({
          title: title.trim(),
          dimension,
          group,
          criteria: [
            ...(useLevel ? [{ kind: "level" as const }] : []),
            ...(usePractice ? [{ kind: "practice" as const, count: practiceCount }] : []),
          ],
        });
      }
      onSaved();
      onClose();
    } catch (caught) {
      if (
        caught instanceof CoachReadinessError
        && caught.status === 409
        && caught.message === "version_conflict"
      ) {
        setConflict(true);
      } else if (caught instanceof CoachReadinessError && caught.message === "limit_reached") {
        setError("You can have three active focus areas.");
      } else {
        setError("Could not save this focus area.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent>
        <div className="overflow-y-auto p-5">
          <DialogTitle className="text-base font-semibold text-[var(--text)]">
            {area ? "Edit focus area" : "Add a focus area"}
          </DialogTitle>
          <DialogDescription className="mt-1 text-sm text-[var(--text-dim)]">
            Keep it small: one thing to work on, with a criterion Hatch can check.
          </DialogDescription>

          <div className="mt-4 grid gap-3">
            <label className="grid gap-1 text-sm text-[var(--text)]">
              Title
              <input
                className={INPUT}
                maxLength={80}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label className="grid gap-1 text-sm text-[var(--text)]">
              Dimension
              <select
                className={INPUT}
                value={dimension}
                onChange={(event) => setDimension(event.target.value)}
              >
                {DIMENSIONS.map((item) => (
                  <option key={item} value={item}>
                    {item.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-sm text-[var(--text)]">
                Role family
                <input
                  className={INPUT}
                  value={roleFamily}
                  onChange={(event) => setRoleFamily(event.target.value)}
                />
              </label>
              <label className="grid gap-1 text-sm text-[var(--text)]">
                Interview type
                <input
                  className={INPUT}
                  value={interviewType}
                  onChange={(event) => setInterviewType(event.target.value)}
                />
              </label>
            </div>
            {!area ? (
              <fieldset className="grid gap-2">
                <legend className="text-sm font-medium text-[var(--text)]">Criteria</legend>
                <label className="flex items-center gap-2 text-sm text-[var(--text)]">
                  <input
                    type="checkbox"
                    checked={useLevel}
                    onChange={(event) => setUseLevel(event.target.checked)}
                  />
                  Reach interview ready in 2 practice sessions
                </label>
                <label className="flex items-center gap-2 text-sm text-[var(--text)]">
                  <input
                    type="checkbox"
                    checked={usePractice}
                    onChange={(event) => setUsePractice(event.target.checked)}
                  />
                  Finish
                  <input
                    type="number"
                    min={1}
                    max={10}
                    aria-label="Plan items to finish"
                    className={`${INPUT} w-20`}
                    value={practiceCount}
                    onChange={(event) => setPracticeCount(Number(event.target.value))}
                  />
                  plan items
                </label>
              </fieldset>
            ) : null}
          </div>

          {conflict ? (
            <p className="mt-3 text-sm text-[var(--danger)]" role="alert">
              This focus area changed. Reload and re-apply. Your draft is kept.
            </p>
          ) : null}
          {error ? (
            <p className="mt-3 text-sm text-[var(--danger)]" role="alert">{error}</p>
          ) : null}

          <div className="mt-5 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="button" loading={saving} onClick={() => void save()}>
              {area ? "Save" : "Add focus area"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
