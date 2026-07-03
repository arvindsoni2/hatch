"use client";
import { useState } from "react";
import { previewJobUrl, saveImportedJob, type JobImportPreview } from "@/lib/api";

export function JobUrlImportModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [url, setUrl] = useState("");
  const [draft, setDraft] = useState<JobImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const extract = async () => { setBusy(true); setError(""); try { setDraft(await previewJobUrl(url)); } catch (e) { setError(e instanceof Error ? e.message : "Could not extract this job page."); } finally { setBusy(false); } };
  const save = async (action: "save_as_job_only" | "save_to_applications" | "save_and_tailor") => {
    if (!draft) return; setBusy(true);
    try {
      const result = await saveImportedJob(draft, action);
      if (action === "save_and_tailor") window.location.assign(`/tailor?applicationId=${result.application_id}`);
      else onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save this job."); } finally { setBusy(false); }
  };
  const field = (key: keyof JobImportPreview, label: string, multiline = false) => <label className="grid gap-1 text-xs" style={{ color: "var(--text-muted)" }}>{label}
    {multiline ? <textarea rows={7} value={String(draft?.[key] ?? "")} onChange={(e) => setDraft(draft ? { ...draft, [key]: e.target.value } : null)} className="rounded-lg p-2" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }} /> :
      <input value={String(draft?.[key] ?? "")} onChange={(e) => setDraft(draft ? { ...draft, [key]: e.target.value } : null)} className="h-11 rounded-lg px-2" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }} />}</label>;
  return <div role="dialog" aria-modal="true" aria-label="Import job from URL" className="fixed inset-0 z-50 grid place-items-center p-4" style={{ background: "rgba(5,7,12,.7)" }}>
    <div className="w-full max-w-2xl max-h-[90vh] overflow-auto rounded-xl p-5 space-y-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="flex justify-between"><div><h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>Import from URL</h2><p className="text-xs" style={{ color: "var(--text-muted)" }}>Extract a public job page, then review every field.</p></div><button onClick={onClose} aria-label="Close">✕</button></div>
      <div className="flex gap-2"><input aria-label="Job URL" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" className="h-11 flex-1 rounded-lg px-3" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }} /><button disabled={busy || !url} onClick={() => void extract()} className="rounded-lg px-4" style={{ background: "var(--accent)", color: "var(--on-accent)" }}>Extract</button></div>
      {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
      {draft ? <><div className="rounded-lg p-3 text-sm" style={{ background: "var(--surface-2)", color: "var(--text)" }}><strong>{draft.confidence.toUpperCase()}</strong> · {draft.confidence === "high" ? "Ready to save" : draft.confidence === "medium" ? "Please review carefully" : "Manual review needed"}{draft.duplicate ? <p>This job is already saved. Opening the existing record.</p> : null}</div>
        <div className="grid grid-cols-2 gap-3">{field("title", "Job title")}{field("company", "Company")}{field("location", "Location")}{field("rate_text", "Salary/rate")}{field("source_url", "Source URL")}{field("apply_url", "Apply URL")}</div>{field("description", "Job description", true)}
        <div className="flex flex-wrap gap-2"><button onClick={() => void save("save_as_job_only")} className="rounded-lg border px-3 py-2">Save as job only</button><button onClick={() => void save("save_to_applications")} className="rounded-lg border px-3 py-2">Save to Applications</button><button onClick={() => void save("save_and_tailor")} className="rounded-lg px-3 py-2" style={{ background: "var(--accent)", color: "var(--on-accent)" }}>Save and Tailor</button></div></> : null}
    </div>
  </div>;
}
