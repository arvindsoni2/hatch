"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { extractDebriefNotes, saveDebrief } from "@/lib/coachReadinessApi";

const MAX_NOTES = 2_500;

export interface DebriefNotesExtractProps {
  roundId: string;
  version: number;
  savedNotes: string | null;
  onDraftSaved: (version: number, notes: string) => void;
  onQuestionsProposed: (texts: string[]) => void;
}

export function DebriefNotesExtract({
  roundId,
  version,
  savedNotes,
  onDraftSaved,
  onQuestionsProposed,
}: DebriefNotesExtractProps) {
  const [notes, setNotes] = useState(savedNotes ?? "");
  const [storedNotes, setStoredNotes] = useState(savedNotes ?? "");
  const [message, setMessage] = useState("");
  const [proposed, setProposed] = useState<string[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const saveDraft = async () => {
    if (busy || !notes.trim()) return;
    setBusy(true);
    setError("");
    try {
      const draft = await saveDebrief(roundId, {
        expected_version: version,
        overall: null,
        notes_text: notes.slice(0, MAX_NOTES),
      });
      setStoredNotes(notes.slice(0, MAX_NOTES));
      onDraftSaved(draft.version, notes);
      setMessage("Notes saved.");
    } catch {
      setError("Could not save the notes. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const extract = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      // Changed notes are saved as a draft before anything reads them.
      const trimmed = notes.slice(0, MAX_NOTES);
      if (trimmed !== storedNotes) {
        const draft = await saveDebrief(roundId, {
          expected_version: version,
          overall: null,
          notes_text: trimmed,
        });
        setStoredNotes(trimmed);
        onDraftSaved(draft.version, trimmed);
      }
      const result = await extractDebriefNotes(roundId);
      setProposed(result.questions);
      setPicked(result.questions);
      if (result.questions.length === 0) setMessage("No questions found in the notes.");
    } catch (failure) {
      const status = (failure as { status?: number }).status;
      setError(
        status === 422
          ? "Save the notes first."
          : "Extraction is unavailable. Add the questions yourself.",
      );
    } finally {
      setBusy(false);
    }
  };

  const addPicked = () => {
    onQuestionsProposed(picked);
    setProposed([]);
    setPicked([]);
  };

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-[var(--text)]" htmlFor="debrief-notes">
        Paste rough notes
      </label>
      <textarea
        id="debrief-notes"
        value={notes}
        onChange={(event) => setNotes(event.target.value.slice(0, MAX_NOTES))}
        rows={4}
        placeholder="Everything you remember about the questions…"
        className="w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text)]"
      />
      <p className="m-0 text-xs text-[var(--text-dim)]">
        {notes.length}/{MAX_NOTES} characters
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => void saveDraft()} disabled={busy || !notes.trim()}>
          Save notes
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => void extract()} disabled={busy || !notes.trim()}>
          Extract questions
        </Button>
        {message ? <span className="text-sm text-[var(--text-dim)]">{message}</span> : null}
        {error ? <span className="text-sm text-[var(--danger)]" role="alert">{error}</span> : null}
      </div>
      {proposed.length > 0 ? (
        <div className="rounded-[var(--radius-card)] bg-[var(--surface-2)] p-3">
          <p className="m-0 text-sm font-semibold text-[var(--text)]">
            Proposed from your notes
          </p>
          <ul className="mt-2 space-y-1">
            {proposed.map((text) => (
              <li key={text}>
                <label className="flex min-h-9 items-center gap-2 text-sm text-[var(--text)]">
                  <input
                    type="checkbox"
                    checked={picked.includes(text)}
                    onChange={() =>
                      setPicked((current) =>
                        current.includes(text)
                          ? current.filter((item) => item !== text)
                          : [...current, text],
                      )
                    }
                  />
                  {text}
                </label>
              </li>
            ))}
          </ul>
          <Button
            type="button"
            size="sm"
            className="mt-2"
            onClick={addPicked}
            disabled={picked.length === 0}
          >
            Add {picked.length} to the checklist
          </Button>
        </div>
      ) : null}
    </div>
  );
}
