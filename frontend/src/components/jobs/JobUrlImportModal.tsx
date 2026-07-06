"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { previewJobUrl, saveImportedJob, type JobImportPreview } from "@/lib/api";

interface JobUrlImportModalProps {
  onClose: () => void;
  onSaved: () => void;
}

export function JobUrlImportModal({ onClose, onSaved }: JobUrlImportModalProps) {
  const [url, setUrl] = useState("");
  const [draft, setDraft] = useState<JobImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const extract = async () => {
    setBusy(true);
    setError("");
    try {
      setDraft(await previewJobUrl(url));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not extract this job page.");
    } finally {
      setBusy(false);
    }
  };

  const save = async (
    action: "save_as_job_only" | "save_to_applications" | "save_and_tailor",
  ) => {
    if (!draft) return;
    setBusy(true);
    try {
      const result = await saveImportedJob(draft, action);
      if (action === "save_and_tailor") {
        window.location.assign(`/tailor?applicationId=${result.application_id}`);
      } else {
        onSaved();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save this job.");
    } finally {
      setBusy(false);
    }
  };

  const field = (key: keyof JobImportPreview, label: string, multiline = false) => {
    const id = `job-import-${key}`;
    const value = String(draft?.[key] ?? "");
    const update = (nextValue: string) => {
      setDraft((current) => current ? { ...current, [key]: nextValue } : null);
    };

    return (
      <label className="grid gap-1.5 text-xs text-[var(--text-muted)]" htmlFor={id}>
        {label}
        {multiline ? (
          <textarea
            className="min-h-40 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text)]"
            id={id}
            name={String(key)}
            onChange={(event) => update(event.target.value)}
            rows={7}
            value={value}
          />
        ) : (
          <Input
            id={id}
            name={String(key)}
            onChange={(event) => update(event.target.value)}
            value={value}
          />
        )}
      </label>
    );
  };

  return (
    <Dialog onOpenChange={(open) => { if (!open && !busy) onClose(); }} open>
      <DialogContent className="max-w-2xl" preventClose={busy}>
        <DialogHeader>
          <DialogTitle>Import from URL</DialogTitle>
          <DialogDescription>
            Extract a public job page, then review every field before saving.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              aria-label="Job URL"
              autoComplete="url"
              name="job_url"
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://example.com/jobs/role…"
              type="url"
              value={url}
            />
            <Button disabled={!url.trim()} loading={busy && !draft} onClick={() => void extract()}>
              Extract
            </Button>
          </div>
          {error ? <p className="text-sm text-[var(--danger)]" role="alert">{error}</p> : null}
          {draft ? (
            <>
              <div className="rounded-[var(--radius-control)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text)]">
                <strong>{draft.confidence.toUpperCase()}</strong>
                {", "}
                {draft.confidence === "high"
                  ? "ready to save"
                  : draft.confidence === "medium"
                    ? "review carefully"
                    : "manual review needed"}
                {draft.duplicate ? <p className="mt-1">This job is already saved.</p> : null}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {field("title", "Job title")}
                {field("company", "Company")}
                {field("location", "Location")}
                {field("rate_text", "Salary or rate")}
                {field("source_url", "Source URL")}
                {field("apply_url", "Apply URL")}
              </div>
              {field("description", "Job description", true)}
            </>
          ) : null}
        </DialogBody>
        {draft ? (
          <DialogFooter>
            <Button disabled={busy} onClick={() => void save("save_as_job_only")} variant="outline">
              Save Job
            </Button>
            <Button disabled={busy} onClick={() => void save("save_to_applications")} variant="secondary">
              Save to Applications
            </Button>
            <Button loading={busy} onClick={() => void save("save_and_tailor")}>
              Save & Tailor
            </Button>
          </DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
