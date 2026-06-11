"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
const API_BASE = "";
import {
  ArrowLeft, Upload, CheckCircle2, AlertCircle, FileText,
  Loader2, RefreshCw, ExternalLink, Save, TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchResumeStatus,
  uploadResume,
  confirmCv,
  type ResumeStatus,
  type ParsePreviewResponse,
} from "@/lib/api";

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionRow({ label, present }: { label: string; present: boolean }) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      {present ? (
        <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
      ) : (
        <AlertCircle className="h-4 w-4 text-amber-400 shrink-0" />
      )}
      <span className="text-sm text-fg">{label}</span>
    </div>
  );
}

interface ExperienceEntry {
  role?: string;
  company?: string;
  period?: string;
  achievements?: Array<{ text: string }>;
}

interface SkillGroup {
  category?: string;
  items?: string[];
}

function ParsePreviewCard({
  preview,
  onConfirm,
  confirming,
}: {
  preview: ParsePreviewResponse;
  onConfirm: () => void;
  confirming: boolean;
}) {
  const cv = preview.parsed_cv;
  const personal = cv.personal as Record<string, string> | undefined;
  const summary = (cv.summary_variants as Record<string, string> | undefined)?.default ?? "";
  const experience = (cv.experience as ExperienceEntry[]) ?? [];
  const skills = (cv.skills as SkillGroup[]) ?? [];
  const certs = (cv.certifications as string[]) ?? [];
  const hasWarnings = preview.warnings.length > 0;

  return (
    <div className="rounded-xl shadow-sm space-y-4" style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>
      {/* Header */}
      <div className="border-b border-border px-5 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-muted" />
          <div>
            <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              {preview.filename}
            </p>
            <p className="text-xs text-muted">Review the extracted data, then click Confirm &amp; Save</p>
          </div>
        </div>
      </div>

      {/* Grounding warnings */}
      {hasWarnings && (
        <div className="mx-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 space-y-1">
          <div className="flex items-center gap-1.5 text-sm font-medium text-amber-800">
            <TriangleAlert className="h-4 w-4 shrink-0" />
            {preview.warnings.length} grounding warning{preview.warnings.length !== 1 ? "s" : ""}
          </div>
          <ul className="text-xs text-amber-700 ml-5 list-disc space-y-0.5">
            {preview.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="px-5 space-y-5 pb-5">
        {/* Personal */}
        {personal && (
          <section>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">Contact</h3>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
              {Object.entries(personal).map(([k, v]) =>
                v ? (
                  <div key={k} className="flex gap-1.5">
                    <dt className="text-muted capitalize">{k.replace("_", " ")}:</dt>
                    <dd className="text-fg truncate">{v}</dd>
                  </div>
                ) : null
              )}
            </dl>
          </section>
        )}

        {/* Summary */}
        {summary && (
          <section>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Summary</h3>
            <p className="text-sm text-fg leading-relaxed line-clamp-4">{summary}</p>
          </section>
        )}

        {/* Experience */}
        {experience.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
              Experience ({experience.length} role{experience.length !== 1 ? "s" : ""})
            </h3>
            <div className="space-y-3">
              {experience.map((exp, i) => (
                <div key={i} className="rounded-lg border border-border bg-[var(--background)] px-3 py-2.5">
                  <p className="text-sm font-medium text-fg">
                    {exp.role || <span className="text-amber-500 italic">role missing</span>}
                  </p>
                  <p className="text-xs text-muted">
                    {exp.company || <span className="text-amber-500 italic">company missing</span>}
                    {exp.period ? ` · ${exp.period}` : ""}
                  </p>
                  {exp.achievements && exp.achievements.length > 0 && (
                    <ul className="mt-1.5 space-y-0.5 list-disc ml-4 text-xs text-muted">
                      {exp.achievements.slice(0, 3).map((a, j) => (
                        <li key={j}>{typeof a === "string" ? a : a.text}</li>
                      ))}
                      {exp.achievements.length > 3 && (
                        <li className="text-muted/60">+{exp.achievements.length - 3} more</li>
                      )}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Skills */}
        {skills.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">Skills</h3>
            <div className="space-y-2">
              {skills.map((grp, i) => (
                <div key={i}>
                  {grp.category && (
                    <p className="text-xs font-medium text-muted mb-1">{grp.category}</p>
                  )}
                  <div className="flex flex-wrap gap-1.5">
                    {(grp.items ?? []).map((item, j) => (
                      <span
                        key={j}
                        className="inline-block rounded-full border border-border px-2 py-0.5 text-xs text-fg"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Certifications */}
        {certs.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Certifications</h3>
            <div className="flex flex-wrap gap-1.5">
              {certs.map((c, i) => (
                <span
                  key={i}
                  className="inline-block rounded-full border border-brand-200 bg-brand-50 px-2 py-0.5 text-xs text-brand-700"
                >
                  {c}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Confirm action */}
        <div className="border-t border-border pt-4 flex items-center gap-3">
          <Button onClick={onConfirm} disabled={confirming}>
            {confirming ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
            ) : (
              <Save className="h-4 w-4 mr-1.5" />
            )}
            Confirm &amp; Save
          </Button>
          <p className="text-xs text-muted">
            {hasWarnings
              ? "Some fields were cleared due to grounding warnings — review above before saving."
              : "This data will be used as the sole source for CV tailoring."}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ResumePage() {
  const [status, setStatus] = useState<ResumeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [preview, setPreview] = useState<ParsePreviewResponse | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const s = await fetchResumeStatus();
      setStatus(s);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleFile = async (file: File) => {
    if (!file.name.endsWith(".docx") && !file.name.endsWith(".pdf")) {
      setUploadError("Only .docx and .pdf files are supported.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    setPreview(null);
    try {
      const result = await uploadResume(file);
      setPreview(result);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const saved = await confirmCv(preview.parsed_cv, preview.filename);
      setStatus(saved);
      setPreview(null);
    } catch (e) {
      setConfirmError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setConfirming(false);
    }
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleFile(file);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-muted" />
      </div>
    );
  }

  const SECTION_LABELS: Record<string, string> = {
    personal: "Contact information",
    summary: "Professional summary",
    experience: "Work experience",
    skills: "Skills",
    education: "Education",
    certifications: "Certifications",
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Nav */}
      <Link href="/settings" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft className="h-4 w-4" /> Settings
      </Link>

      <div>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Master CV</h1>
        <p className="text-sm text-muted mt-1">
          Upload your CV once. Hatch uses it as the <strong>sole source of truth</strong> for
          tailored CVs and cover letters — it never invents content. Supported: <strong>.docx</strong> and <strong>.pdf</strong>.
        </p>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`rounded-xl border-2 border-dashed p-10 text-center transition-colors cursor-pointer ${
          dragOver
            ? "border-brand-400 bg-brand-50"
            : "border-[var(--border)] bg-[var(--surface)] hover:border-brand-300"
        }`}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".docx,.pdf"
          className="hidden"
          onChange={onInputChange}
        />
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50">
          {uploading ? (
            <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
          ) : (
            <Upload className="h-6 w-6 text-brand-600" />
          )}
        </div>
        {uploading ? (
          <div>
            <p className="text-sm font-medium text-fg">Parsing with AI…</p>
            <p className="text-xs text-muted mt-1">Extracting and grounding CV data</p>
          </div>
        ) : (
          <>
            <p className="text-sm font-medium text-fg">
              Drag &amp; drop your CV here, or click to browse
            </p>
            <p className="mt-1 text-xs text-muted">.docx or .pdf · max 10 MB</p>
          </>
        )}
      </div>

      {uploadError && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {uploadError}
        </div>
      )}

      {confirmError && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {confirmError}
        </div>
      )}

      {/* Parse preview — shown after upload, before confirm */}
      {preview && (
        <ParsePreviewCard
          preview={preview}
          onConfirm={() => void handleConfirm()}
          confirming={confirming}
        />
      )}

      {/* Confirmed CV status */}
      {!preview && status && (
        <div className="rounded-xl shadow-sm" style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>
          <div className="border-b border-border px-5 py-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-muted" />
              <div>
                <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {status.filename ?? "master_cv.json"}
                </p>
                {status.uploaded_at && (
                  <p className="text-xs text-muted">
                    Confirmed {new Date(status.uploaded_at).toLocaleDateString("en-GB", {
                      day: "numeric", month: "long", year: "numeric",
                    })}
                  </p>
                )}
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => void load()}>
              <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
            </Button>
          </div>

          {status.parsed && (
            <div className="px-5 py-4 space-y-4">
              <div>
                <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
                  Confirmed sections
                </h3>
                <div className="grid grid-cols-2 gap-x-6">
                  {Object.entries(status.sections).map(([key, present]) => (
                    <SectionRow key={key} label={SECTION_LABELS[key] ?? key} present={present} />
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 border-t border-border pt-4">
                <div className="text-center">
                  <p className="text-2xl font-bold" style={{ color: "var(--text)" }}>{status.skills_count}</p>
                  <p className="text-xs text-muted">skills</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold" style={{ color: "var(--text)" }}>{status.experience_count}</p>
                  <p className="text-xs text-muted">experience roles</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold" style={{ color: "var(--text)" }}>{status.proof_points_count}</p>
                  <p className="text-xs text-muted">proof points</p>
                </div>
              </div>

              <div className="flex items-center gap-3 border-t border-border pt-4">
                <a href={`${API_BASE}/api/resume/json`} target="_blank" rel="noopener noreferrer">
                  <Button variant="outline" size="sm">
                    <ExternalLink className="h-3.5 w-3.5 mr-1" /> View JSON
                  </Button>
                </a>
                <Link href="/settings">
                  <Button variant="outline" size="sm">Edit proof points</Button>
                </Link>
              </div>
            </div>
          )}

          {!status.parsed && status.exists && (
            <div className="px-5 py-4 text-sm text-amber-700">
              CV file exists but could not be parsed. Try re-uploading.
            </div>
          )}
        </div>
      )}

      {!status?.exists && !preview && !loading && (
        <div className="rounded-xl border border-dashed border-amber-200 bg-amber-50 p-6 text-center">
          <AlertCircle className="mx-auto mb-2 h-6 w-6 text-amber-500" />
          <p className="text-sm font-medium text-amber-800">No master CV confirmed</p>
          <p className="mt-1 text-xs text-amber-600">
            Upload your CV above. Tailoring is disabled until you confirm a master CV.
          </p>
        </div>
      )}
    </div>
  );
}
